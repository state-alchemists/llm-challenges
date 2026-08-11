"""
Server log pipeline: Extract log events, transform metrics, and load into
an SQLite database and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration (loaded from environment)
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ErrorEvent:
    """Represents an ERROR line from the log."""
    timestamp: str
    message: str


@dataclass
class WarnEvent:
    """Represents a WARN line from the log."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """Represents a user session line from the log."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEvent:
    """Represents an API latency line from the log."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedEvents:
    """Container for all events extracted from the log file."""
    errors: List[ErrorEvent] = field(default_factory=list)
    warnings: List[WarnEvent] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.+)$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract phase
# ---------------------------------------------------------------------------

def extract_events(log_path: str) -> ParsedEvents:
    """Parse *log_path* and return structured events.

    Each line is matched against a set of regex patterns.  Unrecognised lines
    are silently skipped.
    """
    events = ParsedEvents()

    if not os.path.exists(log_path):
        return events

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            event = _parse_log_line(line)
            if isinstance(event, ErrorEvent):
                events.errors.append(event)
            elif isinstance(event, WarnEvent):
                events.warnings.append(event)
            elif isinstance(event, UserEvent):
                events.user_events.append(event)
            elif isinstance(event, ApiEvent):
                events.api_calls.append(event)

    return events


def _parse_log_line(line: str) -> Optional[ErrorEvent | WarnEvent | UserEvent | ApiEvent]:
    """Parse a single log line and return a typed event, or *None*."""
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return ErrorEvent(timestamp=timestamp, message=message)

    if level == "WARN":
        return WarnEvent(timestamp=timestamp, message=message)

    if level == "INFO":
        user_match = _USER_RE.match(message)
        if user_match:
            return UserEvent(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )

        api_match = _API_RE.match(message)
        if api_match:
            return ApiEvent(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("duration")),
            )

    return None


# ---------------------------------------------------------------------------
# Transform phase
# ---------------------------------------------------------------------------

def transform(events: ParsedEvents) -> Tuple[Dict[str, int], Dict[str, float], int]:
    """Aggregate extracted events into report-ready metrics.

    Returns:
        - error_counts: mapping of error message → occurrence count
        - api_averages: mapping of endpoint → average latency in milliseconds
        - active_sessions: number of users currently logged in
    """
    error_counts = _aggregate_errors(events.errors)
    api_averages = _average_api_latency(events.api_calls)
    active_sessions = _count_active_sessions(events.user_events)
    return error_counts, api_averages, active_sessions


def _aggregate_errors(errors: List[ErrorEvent]) -> Dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: Dict[str, int] = {}
    for event in errors:
        counts[event.message] = counts.get(event.message, 0) + 1
    return counts


def _average_api_latency(api_calls: List[ApiEvent]) -> Dict[str, float]:
    """Compute mean latency per API endpoint."""
    buckets: Dict[str, List[int]] = {}
    for call in api_calls:
        buckets.setdefault(call.endpoint, []).append(call.duration_ms)

    averages: Dict[str, float] = {}
    for endpoint, times in buckets.items():
        averages[endpoint] = sum(times) / len(times)
    return averages


def _count_active_sessions(user_events: List[UserEvent]) -> int:
    """Track log-ins / log-outs and return the number of active sessions."""
    sessions: Dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return len(sessions)


# ---------------------------------------------------------------------------
# Load phase
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg in api_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Render an HTML report from the aggregated metrics."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in api_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _ensure_demo_log(log_path: str) -> None:
    """Create a minimal demo log file if none exists."""
    if os.path.exists(log_path):
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]

    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline."""
    _ensure_demo_log(LOG_FILE)

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    events = extract_events(LOG_FILE)
    error_counts, api_averages, active_sessions = transform(events)
    load_to_database(DB_PATH, error_counts, api_averages)
    generate_report(error_counts, api_averages, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
