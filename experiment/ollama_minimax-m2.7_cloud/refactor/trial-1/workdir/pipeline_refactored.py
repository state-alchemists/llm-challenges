"""
Pipeline: parse server logs, store metrics, generate HTML report.

Architecture follows an Extract → Transform → Load pattern:

    EXTRACT  — read and parse raw log lines into typed entries
    TRANSFORM — aggregate raw entries into summary statistics
    LOAD     — write metrics to DB and produce the HTML report
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: str = os.environ.get("DB_PORT", "5432")
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str          # ERROR | WARN | INFO
    raw: str            # original line, unparsed


@dataclass
class ErrorEntry:
    """An ERROR-level log line."""
    timestamp: str
    message: str


@dataclass
class ApiCallEntry:
    """An INFO line that mentions API."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class SessionEntry:
    """An INFO line that mentions a user action."""
    timestamp: str
    user_id: str
    action: str  # "logged in" | "logged out"


@dataclass
class Metrics:
    """Aggregated statistics from a log run."""
    errors: dict[str, int] = field(default_factory=dict)
    api_calls: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

# Compiled once at import time — each regex is a named capture group.
_RE_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO)"
)
_RE_ERROR = re.compile(r"ERROR (?P<message>.+)")
_RE_API = re.compile(r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms")
_RE_USER = re.compile(r"User (?P<uid>\S+) (?P<action>logged in|logged out)")


def parse_log_line(line: str) -> Optional[LogEntry]:
    """
    Parse a single log line into a LogEntry, or None if it doesn't match.

    Lines look like:
        2024-01-01 12:00:00 INFO User 42 logged in
        2024-01-01 12:05:00 ERROR Database timeout
        2024-01-01 12:08:00 INFO API /users/profile took 250ms
        2024-01-01 12:09:00 WARN Memory usage at 87%
    """
    m = _RE_LOG.match(line.strip())
    if not m:
        return None
    return LogEntry(timestamp=m.group("timestamp"), level=m.group("level"), raw=line)


def extract_entries(log_path: str) -> list[LogEntry]:
    """
    Read *log_path* and return all lines that match the log format.
    Returns an empty list if the file does not exist.
    """
    if not os.path.exists(log_path):
        return []
    with open(log_path) as f:
        return [entry for line in f if (entry := parse_log_line(line))]


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform_to_errors(entries: list[LogEntry]) -> list[ErrorEntry]:
    """Filter ERROR entries and extract structured error messages."""
    result: list[ErrorEntry] = []
    for entry in entries:
        if entry.level == "ERROR":
            m = _RE_ERROR.search(entry.raw)
            msg = m.group("message").strip() if m else entry.raw
            result.append(ErrorEntry(timestamp=entry.timestamp, message=msg))
    return result


def transform_to_api_calls(entries: list[LogEntry]) -> list[ApiCallEntry]:
    """Filter INFO lines that contain API call data."""
    result: list[ApiCallEntry] = []
    for entry in entries:
        if entry.level == "INFO":
            m = _RE_API.search(entry.raw)
            if m:
                result.append(ApiCallEntry(
                    timestamp=entry.timestamp,
                    endpoint=m.group("endpoint"),
                    duration_ms=int(m.group("ms")),
                ))
    return result


def transform_to_sessions(entries: list[LogEntry]) -> list[SessionEntry]:
    """Filter INFO lines that describe user actions."""
    result: list[SessionEntry] = []
    for entry in entries:
        if entry.level == "INFO":
            m = _RE_USER.search(entry.raw)
            if m:
                result.append(SessionEntry(
                    timestamp=entry.timestamp,
                    user_id=m.group("uid"),
                    action=m.group("action"),
                ))
    return result


def aggregate_metrics(
    errors: list[ErrorEntry],
    api_calls: list[ApiCallEntry],
    sessions: list[SessionEntry],
) -> Metrics:
    """
    Collapse raw entries into summary statistics:

    * error message → occurrence count
    * endpoint → list of duration_ms values
    * user_id → timestamp (last-seen); entries with "logged out" are removed
    """
    metrics = Metrics()

    for err in errors:
        metrics.errors[err.message] = metrics.errors.get(err.message, 0) + 1

    for call in api_calls:
        metrics.api_calls.setdefault(call.endpoint, []).append(call.duration_ms)

    active: dict[str, str] = {}
    for sess in sessions:
        if sess.action == "logged in":
            active[sess.user_id] = sess.timestamp
        elif sess.action == "logged out" and sess.user_id in active:
            del active[sess.user_id]
    metrics.active_sessions = active

    return metrics


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables when they do not exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_errors(conn: sqlite3.Connection, errors: dict[str, int]) -> None:
    """
    Upsert error counts using parameterized queries.

    Uses INSERT OR REPLACE so rerunning the pipeline does not duplicate rows.
    """
    now = datetime.datetime.now().isoformat()
    for msg, count in errors.items():
        conn.execute(
            "INSERT OR REPLACE INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )


def load_api_metrics(conn: sqlite3.Connection, api_calls: dict[str, list[int]]) -> None:
    """
    Write per-endpoint average latency using a parameterized query.
    """
    now = datetime.datetime.now().isoformat()
    for endpoint, times in api_calls.items():
        avg = sum(times) / len(times)
        conn.execute(
            "INSERT OR REPLACE INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )


def generate_html_report(metrics: Metrics) -> str:
    """
    Render *metrics* into the same HTML structure as the original script:

    * Error Summary (unordered list)
    * API Latency table (endpoint, avg ms)
    * Active Session count
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in metrics.errors.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.extend([
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])
    for endpoint, times in metrics.api_calls.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.extend([
        "<h2>Active Sessions</h2>",
        f"<p>{len(metrics.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    End-to-end pipeline entry point.

    Extract log entries from ``LOG_FILE``,
    aggregate them into metrics,
    store results in ``DB_PATH``,
    and write ``report.html``.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # EXTRACT
    raw_entries = extract_entries(LOG_FILE)

    # TRANSFORM
    errors = transform_to_errors(raw_entries)
    api_calls = transform_to_api_calls(raw_entries)
    sessions = transform_to_sessions(raw_entries)
    metrics = aggregate_metrics(errors, api_calls, sessions)

    # LOAD — database
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    load_errors(conn, metrics.errors)
    load_api_metrics(conn, metrics.api_calls)
    conn.commit()
    conn.close()

    # LOAD — report
    report = generate_html_report(metrics)
    with open("report.html", "w") as f:
        f.write(report)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap (creates sample log when file is missing — preserved from original)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
