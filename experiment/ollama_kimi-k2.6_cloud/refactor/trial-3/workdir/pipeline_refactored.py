"""
Log processing pipeline.

Reads server logs, extracts metrics (errors, API latency, active sessions),
persists them to SQLite, and generates an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Config (loaded from environment)
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
REPORT_PATH = os.getenv("REPORT_PATH", "report.html")

# These are retained for logging / future DB backends; SQLite ignores them.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LogRecord:
    """A single parsed log record."""

    timestamp: str
    level: str
    message: str


@dataclass
class ErrorRecord(LogRecord):
    """An ERROR-level log record."""


@dataclass
class WarnRecord(LogRecord):
    """A WARN-level log record."""


@dataclass
class UserRecord(LogRecord):
    """An INFO-level record describing a user action."""

    user_id: str
    action: str


@dataclass
class ApiRecord(LogRecord):
    """An INFO-level record describing an API call."""

    endpoint: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Base: 2024-01-01 12:00:00 LEVEL message...
_BASE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<message>.*)$"
)

# User action: User 42 logged in
_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.*)$")

# API call: API /users/profile took 250ms
_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> LogRecord | None:
    """Parse a single log line into a typed record.

    Returns ``None`` if the line does not match the expected format.
    """
    line = line.strip()
    if not line:
        return None

    base_match = _BASE_RE.match(line)
    if not base_match:
        return None

    timestamp = base_match.group("timestamp")
    level = base_match.group("level")
    message = base_match.group("message")

    if level == "ERROR":
        return ErrorRecord(timestamp=timestamp, level=level, message=message)

    if level == "WARN":
        return WarnRecord(timestamp=timestamp, level=level, message=message)

    if level == "INFO":
        if message.startswith("User"):
            user_match = _USER_RE.match(message)
            if user_match:
                return UserRecord(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    user_id=user_match.group("user_id"),
                    action=user_match.group("action"),
                )
        if message.startswith("API"):
            api_match = _API_RE.match(message)
            if api_match:
                return ApiRecord(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    endpoint=api_match.group("endpoint"),
                    duration_ms=int(api_match.group("duration")),
                )

    # Unrecognised INFO line — fall back to a plain LogRecord so we don't drop data.
    return LogRecord(timestamp=timestamp, level=level, message=message)


def extract(log_path: str) -> list[LogRecord]:
    """Read *log_path* and return a list of parsed ``LogRecord`` objects."""
    records: list[LogRecord] = []
    path = Path(log_path)
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = parse_log_line(line)
            if record is not None:
                records.append(record)
    return records


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@dataclass
class TransformedData:
    """Aggregated results ready for loading."""

    error_summary: dict[str, int] = field(default_factory=dict)
    """Mapping of error message → occurrence count."""

    api_latency: dict[str, float] = field(default_factory=dict)
    """Mapping of endpoint → average latency in milliseconds."""

    active_sessions: dict[str, str] = field(default_factory=dict)
    """Mapping of user_id → login timestamp for currently active sessions."""


def transform(records: list[LogRecord]) -> TransformedData:
    """Aggregate *records* into error counts, API averages, and active sessions."""
    data = TransformedData()

    api_times: dict[str, list[int]] = {}

    for record in records:
        if isinstance(record, ErrorRecord):
            data.error_summary[record.message] = (
                data.error_summary.get(record.message, 0) + 1
            )

        elif isinstance(record, UserRecord):
            if record.action == "logged in":
                data.active_sessions[record.user_id] = record.timestamp
            elif record.action == "logged out" and record.user_id in data.active_sessions:
                data.active_sessions.pop(record.user_id)

        elif isinstance(record, ApiRecord):
            api_times.setdefault(record.endpoint, []).append(record.duration_ms)

        elif isinstance(record, WarnRecord):
            # WARN lines are parsed but not included in the error summary
            # (matches original behaviour).
            pass

    for endpoint, times in api_times.items():
        data.api_latency[endpoint] = sum(times) / len(times)

    return data


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create required tables if they do not already exist."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
        """
    )
    conn.commit()


def persist_to_db(
    db_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Write aggregated metrics to SQLite using parameterized queries."""
    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        cursor = conn.cursor()

        for msg, count in error_summary.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, avg_ms in api_latency.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: dict[str, str],
) -> None:
    """Render an HTML report at *report_path*."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, avg in api_latency.items():
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    Path(report_path).write_text("\n".join(lines), encoding="utf-8")


def load(
    db_path: str,
    report_path: str,
    data: TransformedData,
) -> None:
    """Persist *data* to the database and write the HTML report."""
    persist_to_db(db_path, data.error_summary, data.api_latency)
    generate_report(
        report_path,
        data.error_summary,
        data.api_latency,
        data.active_sessions,
    )


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(log_path: str, db_path: str, report_path: str) -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    records = extract(log_path)
    data = transform(records)
    load(db_path, report_path, data)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry-point helpers
# ---------------------------------------------------------------------------

def _seed_demo_log(log_path: str) -> None:
    """Create a minimal demo log file if one does not exist."""
    path = Path(log_path)
    if path.exists():
        return
    path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
        encoding="utf-8",
    )


def main() -> None:
    """CLI entry point."""
    _seed_demo_log(LOG_FILE)
    run_pipeline(LOG_FILE, DB_PATH, REPORT_PATH)


if __name__ == "__main__":
    main()
