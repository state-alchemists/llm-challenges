"""
Server log processing pipeline.

Extracts metrics from server logs, loads them into a SQLite database,
and produces an HTML report.

ETL responsibilities:
  - Extract: parse log lines with regex
  - Transform: aggregate errors and API latency
  - Load: write to DB and emit report.html
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration — all sourced from environment variables with safe defaults
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("PIPELINE_REPORT_FILE", "report.html")


class LogEntry(TypedDict, total=False):
    """Shape of a parsed log record."""
    dt: str          # ISO-ish timestamp, e.g. "2024-01-01 12:00:00"
    t: str           # Record type: ERR | USR | WARN | API
    m: str           # Message (ERR / WARN)
    u: str           # User ID (USR)
    a: str           # Action text (USR)
    endpoint: str    # API endpoint (API)
    ms: int          # Duration in ms (API)


class APICall(TypedDict):
    """Shape of a parsed API call record."""
    dt: str
    endpoint: str
    ms: int


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(r"^(?P<dt>\S+ \S+) (?P<level>ERROR) (?P<msg>.+)$")
_RE_WARN  = re.compile(r"^(?P<dt>\S+ \S+) (?P<level>WARN) (?P<msg>.+)$")
_RE_USER  = re.compile(
    r"^(?P<dt>\S+ \S+) INFO User (?P<uid>\S+) (?P<action>logged in|logged out)"
)
_RE_API   = re.compile(
    r"^(?P<dt>\S+ \S+) INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms"
)

# ---------------------------------------------------------------------------
# EXTRACT — parse a single log line
# ---------------------------------------------------------------------------

def parse_line(line: str) -> LogEntry | None:
    """
    Parse one log line. Returns a LogEntry dict or None if the line
    doesn't match any known format.
    """
    line = line.strip()
    if not line:
        return None

    if (m := _RE_ERROR.match(line)):
        return LogEntry(dt=m["dt"], t="ERR", m=m["msg"])

    if (m := _RE_WARN.match(line)):
        return LogEntry(dt=m["dt"], t="WARN", m=m["msg"])

    if (m := _RE_USER.match(line)):
        return LogEntry(dt=m["dt"], t="USR", u=m["uid"], a=m["action"])

    if (m := _RE_API.match(line)):
        return LogEntry(
            dt=m["dt"], t="API", endpoint=m["endpoint"], ms=int(m["ms"])
        )

    return None


def extract_log_entries(path: str) -> list[LogEntry]:
    """
    Read *path* and return a list of parsed LogEntry records.
    Silently skips unrecognised lines.
    """
    if not os.path.exists(path):
        return []

    entries: list[LogEntry] = []
    with open(path, "r") as fh:
        for raw in fh:
            entry = parse_line(raw)
            if entry is not None:
                entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate raw entries into summary data structures
# ---------------------------------------------------------------------------

def build_session_tracker(
    entries: list[LogEntry],
) -> dict[str, str]:
    """
    Walk USR entries in order and return a dict of currently-active
    sessions: {user_id: last_seen_timestamp}.
    A user is active from their first "logged in" until a "logged out".
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if e.get("t") == "USR":
            uid = e.get("u", "")
            action = e.get("a", "")
            if action == "logged in":
                sessions[uid] = e.get("dt", "")
            elif action == "logged out" and uid in sessions:
                del sessions[uid]
    return sessions


def build_error_summary(entries: list[LogEntry]) -> dict[str, int]:
    """
    Count occurrences of each distinct ERROR message.
    Returns {error_message: count}.
    """
    counts: dict[str, int] = {}
    for e in entries:
        if e.get("t") == "ERR":
            msg = e.get("m", "")
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def build_api_latency(entries: list[LogEntry]) -> dict[str, list[int]]:
    """
    Collect per-endpoint duration lists.
    Returns {endpoint: [duration_ms, ...]}.
    """
    latency: dict[str, list[int]] = {}
    for e in entries:
        if e.get("t") == "API":
            ep = e.get("endpoint", "")
            ms = e.get("ms", 0)
            latency.setdefault(ep, []).append(ms)
    return latency


# ---------------------------------------------------------------------------
# LOAD — write to DB and produce HTML report
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create the two metric tables if they don't already exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_errors(conn: sqlite3.Connection, summary: dict[str, int]) -> None:
    """
    Write aggregated error counts into the *errors* table using a
    parameterised INSERT to prevent SQL injection.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for msg, count in summary.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def load_api_metrics(
    conn: sqlite3.Connection, latency: dict[str, list[int]]
) -> None:
    """
    Write per-endpoint average latencies into the *api_metrics* table
    using a parameterised INSERT.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for ep, times in latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )
    conn.commit()


def render_report(
    path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
) -> None:
    """
    Write the HTML report covering error counts, API latency averages,
    and active session count.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_summary.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, times in api_latency.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Full ETL run:
      1. Extract log entries from LOG_FILE
      2. Transform into session, error, and latency summaries
      3. Load summaries into the DB and write the HTML report
    """
    # EXTRACT
    entries = extract_log_entries(LOG_FILE)

    # TRANSFORM
    active_sessions = build_session_tracker(entries)
    error_summary   = build_error_summary(entries)
    api_latency     = build_api_latency(entries)

    # LOAD — DB
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    load_errors(conn, error_summary)
    load_api_metrics(conn, api_latency)
    conn.close()

    # LOAD — HTML report
    render_report(REPORT_FILE, error_summary, api_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap — create a minimal sample log when none exists (dev convenience)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as fh:
            fh.write("\n".join(sample_lines) + "\n")

    run_pipeline()
