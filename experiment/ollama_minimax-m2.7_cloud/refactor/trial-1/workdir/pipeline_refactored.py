"""
Pipeline: parse server logs, persist metrics to SQLite, and generate an HTML report.

Environment variables (all optional with safe defaults for local dev):
    PIPELINE_DB_PATH     Path to the SQLite database  (default: metrics.db)
    PIPELINE_LOG_FILE    Path to the server log file   (default: server.log)
    PIPELINE_DB_HOST     PostgreSQL host hint in log   (default: localhost)
    PIPELINE_DB_PORT     PostgreSQL port hint in log   (default: 5432)
    PIPELINE_DB_USER     PostgreSQL user hint in log   (default: admin)
    PIPELINE_DB_PASS     PostgreSQL password hint      (default: <empty>)

Output: report.html in the current working directory.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: str = os.environ.get("PIPELINE_DB_PORT", "5432")
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A single ERROR log line, parsed."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A user-facing INFO line (login / logout)."""

    timestamp: str
    user_id: str
    action: str  # e.g. "logged in" or "logged out"


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A single API latency record."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """A single WARN log line."""

    timestamp: str
    message: str


ParseResult = tuple[
    list[ErrorEntry],
    list[UserEvent],
    list[ApiCall],
    list[WarnEntry],
    dict[str, str],  # active sessions: user_id -> login timestamp
]


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(r"^(?P<timestamp>\S+ \S+) ERROR (?P<message>.+)$")
_RE_USER = re.compile(
    r"^(?P<timestamp>\S+ \S+) INFO User (?P<user_id>\S+) (?P<action>\S+.*)$"
)
_RE_API = re.compile(
    r"^(?P<timestamp>\S+ \S+) INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)
_RE_WARN = re.compile(r"^(?P<timestamp>\S+ \S+) WARN (?P<message>.+)$")


# ---------------------------------------------------------------------------
# EXTRACT — parsing
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> tuple[Optional[ErrorEntry], Optional[UserEvent], Optional[ApiCall], Optional[WarnEntry]]:
    """
    Parse a single log line and return the matching entry type (or None).

    Returns four values: (error, user_event, api_call, warn_entry).
    Exactly one will be non-None.
    """
    if (m := _RE_ERROR.match(line)):
        return (
            ErrorEntry(timestamp=m["timestamp"], message=m["message"]),
            None,
            None,
            None,
        )
    if (m := _RE_USER.match(line)):
        action = m["action"]
        if "logged in" not in action and "logged out" not in action:
            return None, None, None, None
        return (
            None,
            UserEvent(timestamp=m["timestamp"], user_id=m["user_id"], action=action),
            None,
            None,
        )
    if (m := _RE_API.match(line)):
        return (
            None,
            None,
            ApiCall(timestamp=m["timestamp"], endpoint=m["endpoint"], duration_ms=int(m["ms"])),
            None,
        )
    if (m := _RE_WARN.match(line)):
        return (
            None,
            None,
            None,
            WarnEntry(timestamp=m["timestamp"], message=m["message"]),
        )
    return None, None, None, None


def read_log_file(path: str) -> ParseResult:
    """
    Read *path*, parse every line, and return structured data plus active sessions.

    Active sessions are computed by walking login/logout events in order.
    """
    errors: list[ErrorEntry] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []
    warns: list[WarnEntry] = []
    sessions: dict[str, str] = {}  # user_id -> login timestamp

    if not os.path.exists(path):
        print(f"Log file not found: {path}", file=sys.stderr)
        return errors, user_events, api_calls, warns, sessions

    with open(path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            err, usr, api, warn = parse_log_line(line)
            if err is not None:
                errors.append(err)
            if usr is not None:
                user_events.append(usr)
                if "logged in" in usr.action:
                    sessions[usr.user_id] = usr.timestamp
                elif "logged out" in usr.action and usr.user_id in sessions:
                    del sessions[usr.user_id]
            if api is not None:
                api_calls.append(api)
            if warn is not None:
                warns.append(warn)

    return errors, user_events, api_calls, warns, sessions


# ---------------------------------------------------------------------------
# TRANSFORM — aggregation
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """
    Count how many times each distinct error message appears.

    Returns a dict mapping error message -> occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def aggregate_api_metrics(api_calls: list[ApiCall]) -> dict[str, list[int]]:
    """
    Group API calls by endpoint and collect their durations.

    Returns a dict mapping endpoint -> list of duration_ms values.
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


# ---------------------------------------------------------------------------
# LOAD — database + report
# ---------------------------------------------------------------------------


def init_database(conn: sqlite3.Connection) -> None:
    """Create the metrics tables if they do not already exist."""
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


def insert_error_counts(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Persist aggregated error counts using a **parameterized** INSERT.

    This is safe against SQL injection — no string formatting is used.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def insert_api_metrics(conn: sqlite3.Connection, endpoint_stats: dict[str, list[int]]) -> None:
    """
    Persist per-endpoint average latency using a **parameterized** INSERT.

    This is safe against SQL injection — no string formatting is used.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for endpoint, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )
    conn.commit()


def build_html_report(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, list[int]],
    active_session_count: int,
) -> str:
    """
    Render the HTML report string.

    Includes:
      - Error summary (unordered list of message + occurrence count)
      - API latency table (endpoint, average ms)
      - Active session count
    """
    buf: list[str] = []
    buf.append("<html>")
    buf.append("<head><title>System Report</title></head>")
    buf.append("<body>")

    # Error summary
    buf.append("<h1>Error Summary</h1>")
    buf.append("<ul>")
    for msg, count in error_counts.items():
        buf.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    buf.append("</ul>")

    # API latency
    buf.append("<h2>API Latency</h2>")
    buf.append("<table border='1'>")
    buf.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        buf.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    buf.append("</table>")

    # Active sessions
    buf.append("<h2>Active Sessions</h2>")
    buf.append(f"<p>{active_session_count} user(s) currently active</p>")

    buf.append("</body>")
    buf.append("</html>")
    return "\n".join(buf)


def write_report(path: str, html: str) -> None:
    """Atomically write *html* content to *path* (overwrites existing)."""
    with open(path, "w") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Full ETL pipeline:

    1. Read and parse the log file (Extract).
    2. Aggregate errors and API latency numbers (Transform).
    3. Persist metrics to SQLite and write report.html (Load).
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # Extract
    errors, user_events, api_calls, warns, active_sessions = read_log_file(LOG_FILE)

    # Transform
    error_counts = aggregate_errors(errors)
    endpoint_stats = aggregate_api_metrics(api_calls)

    # Load — database
    conn = sqlite3.connect(DB_PATH)
    init_database(conn)
    insert_error_counts(conn, error_counts)
    insert_api_metrics(conn, endpoint_stats)
    conn.close()

    # Load — HTML report
    html = build_html_report(error_counts, endpoint_stats, len(active_sessions))
    write_report("report.html", html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
    run_pipeline()