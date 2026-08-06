"""
Server log processing pipeline.

Extracts events from server logs, aggregates metrics into SQLite,
and produces an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import ClassVar


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A single error message with a running count."""
    message: str
    count: int = 0


@dataclass
class ApiMetricEntry:
    """Latency record for an API endpoint."""
    dt: str
    endpoint: str
    avg_ms: float


@dataclass
class ParsedLogEntry:
    """Result of parsing a single log line."""
    dt: str
    level: str
    raw: str
    # Optional fields populated according to log type
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    warning_message: str | None = None


# ---------------------------------------------------------------------------
# Regex patterns (compiled once, reused)
# ---------------------------------------------------------------------------

_TIMESTAMP_RE: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
)
_LEVEL_RE: re.Pattern[str] = re.compile(r"^(?P<timestamp>[\d-]+ [\d:]+) (?P<level>ERROR|INFO|WARN) ")
_ERROR_RE: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>[\d-]+ [\d:]+) ERROR (?P<message>.+)$"
)
_WARN_RE: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>[\d-]+ [\d:]+) WARN (?P<message>.+)$"
)
_USER_RE: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>[\d-]+ [\d:]+) INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_API_RE: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>[\d-]+ [\d:]+) INFO API (?P<endpoint>\S+) "
    r"took (?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def read_log_lines(path: str) -> list[str]:
    """
    Return all non-empty, non-whitespace-only lines from *path*.

    Parameters
    ----------
    path:
        Absolute or relative path to the server log file.

    Returns
    -------
    List of raw log line strings, in file order.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------

def parse_log_entry(line: str) -> ParsedLogEntry | None:
    """
    Parse a single log line into a structured :class:`ParsedLogEntry`.

    Tries each pattern in order of specificity and returns ``None`` if
    no pattern matches.

    Parameters
    ----------
    line:
        A single raw log line.

    Returns
    -------
    A :class:`ParsedLogEntry` when the line is recognised, otherwise ``None``.
    """
    # ERROR lines
    m = _ERROR_RE.match(line)
    if m:
        return ParsedLogEntry(
            dt=m["timestamp"],
            level="ERROR",
            raw=line,
            error_message=m["message"].strip(),
        )

    # WARN lines
    m = _WARN_RE.match(line)
    if m:
        return ParsedLogEntry(
            dt=m["timestamp"],
            level="WARN",
            raw=line,
            warning_message=m["message"].strip(),
        )

    # User activity (INFO ... User ...)
    m = _USER_RE.match(line)
    if m:
        action = m["action"].strip()
        return ParsedLogEntry(
            dt=m["timestamp"],
            level="INFO",
            raw=line,
            user_id=m["uid"],
            action=action,
        )

    # API calls (INFO ... API ...)
    m = _API_RE.match(line)
    if m:
        return ParsedLogEntry(
            dt=m["timestamp"],
            level="INFO",
            raw=line,
            endpoint=m["endpoint"],
            latency_ms=int(m["ms"]),
        )

    # Unrecognised – still surface it as an INFO entry with the raw text
    m = _LEVEL_RE.match(line)
    if m:
        return ParsedLogEntry(
            dt=m["timestamp"],
            level=m["level"],
            raw=line,
        )

    return None


def aggregate_errors(entries: list[ParsedLogEntry]) -> dict[str, int]:
    """
    Count occurrences of each distinct error message.

    Parameters
    ----------
    entries:
        Parsed log entries.

    Returns
    -------
    A mapping from error message text to its total occurrence count.
    """
    counts: dict[str, int] = {}
    for e in entries:
        if e.level == "ERROR" and e.error_message:
            counts[e.error_message] = counts.get(e.error_message, 0) + 1
    return counts


def aggregate_api_latency(entries: list[ParsedLogEntry]) -> dict[str, list[int]]:
    """
    Collect per-endpoint latency samples.

    Parameters
    ----------
    entries:
        Parsed log entries.

    Returns
    -------
    A mapping from endpoint path to a list of observed latencies in ms.
    """
    stats: dict[str, list[int]] = {}
    for e in entries:
        if e.level == "INFO" and e.endpoint and e.latency_ms is not None:
            stats.setdefault(e.endpoint, []).append(e.latency_ms)
    return stats


def compute_active_sessions(entries: list[ParsedLogEntry]) -> int:
    """
    Count currently-active sessions based on login/logout events.

    A user is considered active from their most recent login until
    their next explicit logout.  Nested or out-of-order logins are
    counted each time (re-login re-activates).

    Parameters
    ----------
    entries:
        Parsed log entries.

    Returns
    -------
    The number of sessions that are still open at the end of the log.
    """
    open_sessions: set[str] = set()
    for e in entries:
        if e.level == "INFO" and e.user_id and e.action:
            if "logged in" in e.action:
                open_sessions.add(e.user_id)
            elif "logged out" in e.action:
                open_sessions.discard(e.user_id)
    return len(open_sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """
    Create the pipeline's metric tables if they do not already exist.

    Parameters
    ----------
    conn:
        An open SQLite connection.
    """
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


def load_error_counts(conn: sqlite3.Connection, counts: dict[str, int]) -> None:
    """
    Write error aggregation rows into the ``errors`` table.

    Uses a parameterised INSERT to prevent SQL injection.

    Parameters
    ----------
    conn:
        An open SQLite connection.
    counts:
        Error message → total count mapping from :func:`aggregate_errors`.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    # Parameterised: safe against injection in both `now` and `msg`.
    cur.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in counts.items()],
    )
    conn.commit()


def load_api_metrics(conn: sqlite3.Connection, stats: dict[str, list[int]]) -> None:
    """
    Write per-endpoint average latency rows into the ``api_metrics`` table.

    Uses a parameterised INSERT to prevent SQL injection.

    Parameters
    ----------
    conn:
        An open SQLite connection.
    stats:
        Endpoint → latency samples (ms) mapping from :func:`aggregate_api_latency`.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, sum(vals) / len(vals)) for ep, vals in stats.items()],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def build_html_report(
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """
    Render the aggregated metrics as a self-contained HTML document.

    Parameters
    ----------
    error_counts:
        Error message → count mapping.
    api_stats:
        Endpoint → latency sample list mapping.
    active_sessions:
        Number of currently-open sessions.

    Returns
    -------
    A complete HTML string suitable for writing to ``report.html``.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, cnt in error_counts.items():
        # Minimal HTML escaping – preserve structure, avoid tag injection
        safe_msg = (msg
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))
        lines.append(f"<li><b>{safe_msg}</b>: {cnt} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, vals in api_stats.items():
        avg = sum(vals) / len(vals)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full Extract → Transform → Load pipeline.

    1. Reads and parses ``LOG_FILE``.
    2. Aggregates errors, API latency, and active sessions.
    3. Writes aggregated rows into the SQLite database at ``DB_PATH``.
    4. Emits ``report.html`` with the same information as the original.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # --- Extract ---
    raw_lines = read_log_lines(LOG_FILE)
    parsed = [p for line in raw_lines if (p := parse_log_entry(line)) is not None]

    # --- Transform ---
    error_counts = aggregate_errors(parsed)
    api_stats = aggregate_api_latency(parsed)
    active_sessions = compute_active_sessions(parsed)

    # --- Load ---
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        load_error_counts(conn, error_counts)
        load_api_metrics(conn, api_stats)
    finally:
        conn.close()

    # --- Report ---
    html = build_html_report(error_counts, api_stats, active_sessions)
    with open("report.html", "w") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        # Produce a minimal sample log so the pipeline can run out-of-the-box
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
