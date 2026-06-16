"""Refactored server-log processing pipeline.

Follows an Extract → Transform → Load pattern:
- Extract: parse log lines into structured records using regex.
- Transform: aggregate errors, compute API latency stats, track sessions.
- Load: persist results to SQLite (parameterised queries) and generate report.html.

All configuration is read from environment variables.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration — all values sourced from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """A parsed ERROR or WARN log entry."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A parsed user login/logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """A parsed API latency measurement."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class PipelineResult:
    """Aggregated results ready for reporting."""
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latency: Dict[str, List[int]] = field(default_factory=dict)
    active_session_count: int = 0


# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<message>.*)$"
)

_USER_EVENT_RE = re.compile(
    r"User\s+(?P<user_id>\S+)\s+(?P<action>.*)$"
)

_API_CALL_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<latency>\d+)ms$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_log_records(
    log_path: str,
) -> tuple[List[ErrorRecord], List[UserEvent], List[ApiCall]]:
    """Parse a server log file into structured records using regex.

    Each line is matched against a compiled pattern to extract the timestamp,
    log level, and message body.  Structured INFO lines (user events, API
    calls) are further parsed with dedicated patterns.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A 3-tuple of (errors, user_events, api_calls).
    """
    errors: List[ErrorRecord] = []
    user_events: List[UserEvent] = []
    api_calls: List[ApiCall] = []

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return errors, user_events, api_calls

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line.strip())
            if not match:
                continue

            timestamp: str = match.group("timestamp")
            level: str = match.group("level")
            message: str = match.group("message")

            if level in ("ERROR", "WARN"):
                errors.append(ErrorRecord(
                    timestamp=timestamp, level=level, message=message,
                ))
            elif level == "INFO":
                user_match: Optional[re.Match] = _USER_EVENT_RE.search(message)
                if user_match:
                    user_events.append(UserEvent(
                        timestamp=timestamp,
                        user_id=user_match.group("user_id"),
                        action=user_match.group("action"),
                    ))

                api_match: Optional[re.Match] = _API_CALL_RE.search(message)
                if api_match:
                    api_calls.append(ApiCall(
                        timestamp=timestamp,
                        endpoint=api_match.group("endpoint"),
                        latency_ms=int(api_match.group("latency")),
                    ))

    return errors, user_events, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_records(
    errors: List[ErrorRecord],
    user_events: List[UserEvent],
    api_calls: List[ApiCall],
) -> PipelineResult:
    """Aggregate parsed records into reporting-ready summaries.

    - Counts error/warning messages by occurrence.
    - Groups API latencies by endpoint.
    - Tracks active sessions (logins minus logouts).

    Args:
        errors: Parsed ERROR/WARN records.
        user_events: Parsed user login/logout events.
        api_calls: Parsed API call latency records.

    Returns:
        A PipelineResult with aggregated counts and statistics.
    """
    error_counts: Dict[str, int] = {}
    for err in errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_latency: Dict[str, List[int]] = {}
    for call in api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.latency_ms)

    active_sessions: Dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            active_sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in active_sessions:
            del active_sessions[event.user_id]

    return PipelineResult(
        error_counts=error_counts,
        api_latency=api_latency,
        active_session_count=len(active_sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(result: PipelineResult, db_path: str) -> None:
    """Persist aggregated results to SQLite using parameterised queries.

    Creates tables if they do not exist, then inserts error counts and
    API latency averages.  All inserts use ``?`` placeholders to prevent
    SQL injection.

    Args:
        result: Aggregated pipeline results.
        db_path: Path to the SQLite database file.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn: sqlite3.Connection = sqlite3.connect(db_path)
    cursor: sqlite3.Cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now: str = str(datetime.datetime.now())
    for msg, count in result.error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count)
        )

    for endpoint, latencies in result.api_latency.items():
        avg_latency: float = sum(latencies) / len(latencies)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_latency),
        )

    conn.commit()
    conn.close()


def load_report_html(result: PipelineResult, output_path: str) -> None:
    """Generate an HTML report from aggregated pipeline results.

    The report contains three sections:
    - **Error Summary** — each unique error/warning message with its count.
    - **API Latency** — a table of endpoints and average response times.
    - **Active Sessions** — the number of users currently logged in.

    Args:
        result: Aggregated pipeline results.
        output_path: Path where the HTML report is written.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in result.error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, latencies in result.api_latency.items():
        avg: float = round(sum(latencies) / len(latencies), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{result.active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    errors, user_events, api_calls = extract_log_records(LOG_FILE)
    result: PipelineResult = transform_records(errors, user_events, api_calls)
    load_to_database(result, DB_PATH)
    load_report_html(result, "report.html")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()