"""Server-log processing pipeline: Extract → Transform → Load.

Reads server logs, aggregates errors/API latency/active sessions,
persists metrics to SQLite (parameterised queries), and writes an HTML
report.  All configurable values come from environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration – environment variables with sensible defaults
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables.

    Attributes:
        db_path:      Path to the SQLite database file.
        log_file:     Path to the server log file to process.
        db_host:      Database host (informational; printed at start).
        db_port:      Database port (informational; printed at start).
        db_user:      Database user  (informational; printed at start).
        db_pass:      Database password (not used for SQLite connections).
        report_path:  Path for the generated HTML report.
    """

    db_path: Path
    log_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: Path


def load_config() -> Config:
    """Build a ``Config`` from environment variables, falling back to defaults."""
    return Config(
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        log_file=Path(os.getenv("LOG_FILE", "server.log")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
        report_path=Path(os.getenv("REPORT_PATH", "report.html")),
    )


# ---------------------------------------------------------------------------
# Parsed log-entry types
# ---------------------------------------------------------------------------


class ErrorEntry(NamedTuple):
    """An ERROR-level log entry."""

    timestamp: str
    message: str


class UserEventEntry(NamedTuple):
    """An INFO-level log entry recording a user action."""

    timestamp: str
    user_id: str
    action: str


class ApiCallEntry(NamedTuple):
    """An INFO-level log entry recording an API call with latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


class WarningEntry(NamedTuple):
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class LogData:
    """Categorised log entries produced by the Extract phase."""

    errors: list[ErrorEntry]
    user_events: list[UserEventEntry]
    api_calls: list[ApiCallEntry]
    warnings: list[WarningEntry]


# ---------------------------------------------------------------------------
# Extract – regex-based log parsing
# ---------------------------------------------------------------------------

# 2024-01-01 12:05:00 ERROR Database timeout
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<payload>.+)$"
)

# User 42 logged in
_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# API /users/profile took 250ms
_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


def _parse_line(line: str) -> ErrorEntry | UserEventEntry | ApiCallEntry | WarningEntry | None:
    """Parse a single log line into a typed entry.

    Returns ``None`` for lines that don't match the expected format.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    payload = match.group("payload")

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, message=payload)

    if level == "WARN":
        return WarningEntry(timestamp=timestamp, message=payload)

    # INFO lines – dispatch on payload prefix
    user_match = _USER_RE.match(payload)
    if user_match:
        return UserEventEntry(
            timestamp=timestamp,
            user_id=user_match.group("user_id"),
            action=user_match.group("action"),
        )

    api_match = _API_RE.match(payload)
    if api_match:
        duration = int(api_match.group("duration")) if api_match.group("duration") else 0
        return ApiCallEntry(
            timestamp=timestamp,
            endpoint=api_match.group("endpoint"),
            duration_ms=duration,
        )

    return None


def extract(log_file: Path) -> LogData:
    """Read *log_file* and return categorised entries.

    Returns an empty ``LogData`` when the file does not exist.
    """
    data = LogData(errors=[], user_events=[], api_calls=[], warnings=[])

    if not log_file.exists():
        return data

    with log_file.open("r") as fh:
        for line in fh:
            entry = _parse_line(line)
            if isinstance(entry, ErrorEntry):
                data.errors.append(entry)
            elif isinstance(entry, UserEventEntry):
                data.user_events.append(entry)
            elif isinstance(entry, ApiCallEntry):
                data.api_calls.append(entry)
            elif isinstance(entry, WarningEntry):
                data.warnings.append(entry)

    return data


# ---------------------------------------------------------------------------
# Transform – aggregation helpers
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def aggregate_api_latency(api_calls: list[ApiCallEntry]) -> dict[str, list[int]]:
    """Group API-call durations by endpoint."""
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def compute_active_sessions(user_events: list[UserEventEntry]) -> dict[str, str]:
    """Track login/logout events and return currently active sessions.

    Returns a mapping of ``user_id → login_timestamp`` for users who
    have logged in but not yet logged out.
    """
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            del sessions[event.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load – database persistence
# ---------------------------------------------------------------------------


def _init_db(conn: sqlite3.Connection) -> None:
    """Create pipeline tables if they do not already exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_error_counts(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """Insert aggregated error counts using parameterised queries."""
    cur = conn.cursor()
    now = str(datetime.datetime.now())
    for message, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )


def load_api_metrics(
    conn: sqlite3.Connection, endpoint_stats: dict[str, list[int]]
) -> None:
    """Insert average API latencies using parameterised queries."""
    cur = conn.cursor()
    now = str(datetime.datetime.now())
    for endpoint, times in endpoint_stats.items():
        avg_ms = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )


# ---------------------------------------------------------------------------
# Load – HTML report generation
# ---------------------------------------------------------------------------


def generate_report(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, list[int]],
    active_sessions: dict[str, str],
) -> str:
    """Render the HTML report containing error summary, API latency table,
    and active-session count.
    """
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
    for endpoint, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def write_report(report: str, path: Path) -> None:
    """Write the HTML report to *path*."""
    path.write_text(report)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline(config: Config) -> None:
    """Execute the full ETL pipeline: Extract → Transform → Load."""
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    # Extract
    log_data = extract(config.log_file)

    # Transform
    error_counts = aggregate_errors(log_data.errors)
    endpoint_stats = aggregate_api_latency(log_data.api_calls)
    active_sessions = compute_active_sessions(log_data.user_events)

    # Load – database
    conn = sqlite3.connect(config.db_path)
    try:
        _init_db(conn)
        load_error_counts(conn, error_counts)
        load_api_metrics(conn, endpoint_stats)
        conn.commit()
    finally:
        conn.close()

    # Load – report
    report = generate_report(error_counts, endpoint_stats, active_sessions)
    write_report(report, config.report_path)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)

if __name__ == "__main__":
    cfg = load_config()
    if not cfg.log_file.exists():
        cfg.log_file.write_text(_SAMPLE_LOG)
    run_pipeline(cfg)