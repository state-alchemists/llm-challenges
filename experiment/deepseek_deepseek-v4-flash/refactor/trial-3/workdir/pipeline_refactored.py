"""
Server log processing pipeline — extracts structured events from log files,
transforms them into aggregates (error summary, API latencies, session
activity), and loads results into SQLite and an HTML report.

Usage:
    LOG_FILE_PATH=server.log DB_PATH=metrics.db python pipeline_refactored.py
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

LOG_FILE_PATH: str = os.environ.get("LOG_FILE_PATH", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

class LogEntry(NamedTuple):
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Extract — parse log file into structured records
# ---------------------------------------------------------------------------

# Matches: YYYY-MM-DD HH:MM:SS LEVEL free-form message…
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR|INFO|WARN) (.+)$"
)
# Sub-patterns for recognized INFO lines
_USER_ACTION_RE = re.compile(r"^User (\S+) (.+)$")
_API_CALL_RE = re.compile(r"^API (\S+) took (\d+)ms$")


def parse_log_line(raw: str) -> LogEntry | None:
    """Parse a single log line into a structured LogEntry.

    Returns ``None`` for blank, unparseable, or out-of-spec lines.
    """
    raw = raw.strip()
    if not raw:
        return None

    m = _LOG_LINE_RE.match(raw)
    if not m:
        return None

    timestamp, level, rest = m.groups()

    if level == "ERROR":
        return LogEntry(timestamp=timestamp, level=level, message=rest)

    if level == "WARN":
        return LogEntry(timestamp=timestamp, level=level, message=rest)

    # level == "INFO" — try sub-patterns
    user_m = _USER_ACTION_RE.match(rest)
    if user_m:
        uid, action = user_m.groups()
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=rest,
            user_id=uid,
            action=action,
        )

    api_m = _API_CALL_RE.match(rest)
    if api_m:
        endpoint, duration_str = api_m.groups()
        duration_ms = int(duration_str)
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=rest,
            endpoint=endpoint,
            duration_ms=duration_ms,
        )

    # Unrecognised INFO — still capture as basic info
    return LogEntry(timestamp=timestamp, level=level, message=rest)


def extract_logs(path: str) -> list[LogEntry]:
    """Read and parse every line in *path*; skip malformed lines silently."""
    if not os.path.exists(path):
        print(f"Warning: log file not found at {path!r}, returning empty input.")
        return []

    entries: list[LogEntry] = []
    with open(path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate parsed data into report components
# ---------------------------------------------------------------------------

class ErrorSummary(NamedTuple):
    """Aggregated error counts keyed by error message."""

    counts: dict[str, int]


class ApiLatency(NamedTuple):
    """Per-endpoint average latency in milliseconds."""

    averages: dict[str, float]


class SessionTracker(NamedTuple):
    """Active-session state derived from user login/logout events."""

    active_count: int


def count_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Return a mapping of error message → occurrence count."""
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.level == "ERROR":
            counts[e.message] += 1
    return dict(counts)


def compute_api_latencies(entries: list[LogEntry]) -> dict[str, float]:
    """Return a mapping of endpoint → average response time (ms).

    Endpoints without timing data are omitted.
    """
    durations: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        if e.endpoint is not None and e.duration_ms is not None:
            durations[e.endpoint].append(e.duration_ms)
    return {ep: sum(times) / len(times) for ep, times in durations.items()}


def track_active_sessions(entries: list[LogEntry]) -> int:
    """Return the number of sessions still active after processing all events."""
    sessions: dict[str, str] = {}  # user_id → login timestamp
    for e in entries:
        if e.level == "INFO" and e.user_id is not None and e.action is not None:
            if "logged in" in e.action:
                sessions[e.user_id] = e.timestamp
            elif "logged out" in e.action and e.user_id in sessions:
                del sessions[e.user_id]
    return len(sessions)


def transform(entries: list[LogEntry]) -> tuple[dict[str, int], dict[str, float], int]:
    """Run all transform steps and return (error_counts, api_latencies, active_sessions)."""
    return (
        count_errors(entries),
        compute_api_latencies(entries),
        track_active_sessions(entries),
    )


# ---------------------------------------------------------------------------
# Load — write results to SQLite and HTML
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Create/connect to the SQLite database and ensure tables exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def load_errors_to_db(
    conn: sqlite3.Connection, error_counts: dict[str, int]
) -> None:
    """Insert error aggregate rows using parameterised queries."""
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in error_counts.items()],
    )
    conn.commit()


def load_api_metrics_to_db(
    conn: sqlite3.Connection, api_latencies: dict[str, float]
) -> None:
    """Insert API latency rows using parameterised queries."""
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in api_latencies.items()],
    )
    conn.commit()


def generate_html_report(
    error_counts: dict[str, int],
    api_latencies: dict[str, float],
    active_sessions: int,
    path: str = "report.html",
) -> None:
    """Write a self-contained HTML report to *path*."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in sorted(api_latencies.items()):
        lines.append(f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(log_path: str, db_path: str) -> None:
    """Run the full ETL pipeline: extract → transform → load."""
    print(f"Parsing logs from {log_path!r} …")
    entries = extract_logs(log_path)
    print(f"  Parsed {len(entries)} log entries.")

    print("Transforming …")
    error_counts, api_latencies, active_sessions = transform(entries)

    print(f"Loading into {db_path!r} …")
    conn = init_db(db_path)
    try:
        load_errors_to_db(conn, error_counts)
        load_api_metrics_to_db(conn, api_latencies)
    finally:
        conn.close()

    print("Generating report.html …")
    generate_html_report(error_counts, api_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _ensure_sample_log(path: str) -> None:
    """Create a sample log file when none exists (dev/test convenience)."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(
                "2024-01-01 12:00:00 INFO User 42 logged in\n"
                "2024-01-01 12:05:00 ERROR Database timeout\n"
                "2024-01-01 12:05:05 ERROR Database timeout\n"
                "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
                "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
                "2024-01-01 12:10:00 INFO User 42 logged out\n"
            )


if __name__ == "__main__":
    _ensure_sample_log(LOG_FILE_PATH)
    run_pipeline(LOG_FILE_PATH, DB_PATH)
