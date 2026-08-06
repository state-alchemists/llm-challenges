"""ETL pipeline that parses server logs and produces a metrics report.

Pipeline stages:
    1. Extract  – read and parse raw log lines using regular expressions.
    2. Transform – aggregate error counts, API latency statistics, and active sessions.
    3. Load      – persist aggregates to SQLite and render an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Configuration (loaded from environment with sensible defaults)
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE_PATH: str = os.getenv("LOG_FILE_PATH", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class ParsedLogLine:
    """A single log line broken into its constituent parts."""

    timestamp: str
    level: str
    message: str


@dataclass
class SessionEvent:
    """A user login or logout event extracted from an INFO line."""

    timestamp: str
    user_id: str
    action: str  # e.g. "logged in", "logged out"


@dataclass
class ApiCall:
    """An API call with its measured latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class TransformedData:
    """Aggregated metrics ready for the Load stage."""

    error_counts: Dict[str, int] = field(default_factory=dict)
    endpoint_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
)
_USER_EVENT_RE = re.compile(r"User (\d+) (.+)")
_API_CALL_RE = re.compile(r"API (\S+)(?: took (\d+)ms)?")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def ensure_sample_log_file(path: str) -> None:
    """Create a sample log file if one does not already exist."""
    if os.path.exists(path):
        return
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines) + "\n")


def parse_log_line(line: str) -> ParsedLogLine | None:
    """Parse a single log line into a structured record.

    Args:
        line: Raw text line from the log file.

    Returns:
        A ``ParsedLogLine`` on success, or ``None`` if the line does not match
        the expected format.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None
    timestamp, level, message = match.groups()
    return ParsedLogLine(timestamp=timestamp, level=level, message=message)


def extract(log_path: str) -> tuple[List[ParsedLogLine], List[SessionEvent], List[ApiCall]]:
    """Read the log file and extract raw records.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A tuple of ``(general_lines, session_events, api_calls)``.
    """
    general_lines: List[ParsedLogLine] = []
    session_events: List[SessionEvent] = []
    api_calls: List[ApiCall] = []

    with open(log_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            parsed = parse_log_line(raw_line)
            if parsed is None:
                continue

            if parsed.level == "INFO":
                user_match = _USER_EVENT_RE.search(parsed.message)
                if user_match:
                    user_id, action = user_match.groups()
                    session_events.append(
                        SessionEvent(
                            timestamp=parsed.timestamp,
                            user_id=user_id,
                            action=action,
                        )
                    )
                    continue

                api_match = _API_CALL_RE.match(parsed.message)
                if api_match:
                    endpoint, duration_str = api_match.groups()
                    duration_ms = int(duration_str) if duration_str else 0
                    api_calls.append(
                        ApiCall(
                            timestamp=parsed.timestamp,
                            endpoint=endpoint,
                            duration_ms=duration_ms,
                        )
                    )
                    continue

            general_lines.append(parsed)

    return general_lines, session_events, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def transform(
    general_lines: List[ParsedLogLine],
    session_events: List[SessionEvent],
    api_calls: List[ApiCall],
) -> TransformedData:
    """Aggregate raw records into metrics suitable for reporting.

    Args:
        general_lines: All non-session, non-API log lines (ERROR, WARN, etc.).
        session_events: User login / logout events.
        api_calls: Individual API call latency measurements.

    Returns:
        A ``TransformedData`` object containing error counts, endpoint
        latencies, and the current active-session snapshot.
    """
    data = TransformedData()

    # Aggregate ERROR messages by message text
    for line in general_lines:
        if line.level == "ERROR":
            data.error_counts[line.message] = data.error_counts.get(line.message, 0) + 1

    # Collect latencies per endpoint
    for call in api_calls:
        data.endpoint_latencies.setdefault(call.endpoint, []).append(call.duration_ms)

    # Replay session events to determine active sessions
    for event in session_events:
        if "logged in" in event.action:
            data.active_sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in data.active_sessions:
            data.active_sessions.pop(event.user_id)

    return data


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_to_database(db_path: str, data: TransformedData) -> None:
    """Persist transformed metrics to a SQLite database.

    Uses parameterized queries to eliminate SQL-injection risk.

    Args:
        db_path: Path to the SQLite database file.
        data: Aggregated metrics from the Transform stage.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    for message, count in data.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in data.endpoint_latencies.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(data: TransformedData, output_path: str) -> None:
    """Render an HTML report from the transformed metrics.

    Args:
        data: Aggregated metrics from the Transform stage.
        output_path: Destination path for the generated ``report.html``.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, times in data.endpoint_latencies.items():
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(data.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def load(data: TransformedData, db_path: str, report_path: str) -> None:
    """Execute the Load stage: persist to DB and render the HTML report.

    Args:
        data: Aggregated metrics from the Transform stage.
        db_path: Path to the SQLite database file.
        report_path: Destination path for ``report.html``.
    """
    load_to_database(db_path, data)
    generate_html_report(data, report_path)
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    ensure_sample_log_file(LOG_FILE_PATH)

    general_lines, session_events, api_calls = extract(LOG_FILE_PATH)
    data = transform(general_lines, session_events, api_calls)
    load(data, DB_PATH, "report.html")


if __name__ == "__main__":
    run_pipeline()
