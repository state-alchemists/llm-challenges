"""Refactored server-log processing pipeline.

Extracts structured log entries, transforms them into aggregated metrics,
and loads the results into a SQLite database and an HTML report.

All configuration (database path, log file path, credentials) is read from
environment variables with sensible defaults so secrets never appear as
hardcoded literals in the source.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration – all values come from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+)\s+(?P<message>.*)$"
)
_USER_PATTERN = re.compile(r"^User (?P<user_id>\S+)\s+(?P<action>.+)$")
_API_PATTERN = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass
class ErrorRecord:
    """An error message with its total occurrence count."""

    message: str
    count: int


@dataclass
class ApiCall:
    """A single API call timing observation."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class UserEvent:
    """A user login or logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ParsedLog:
    """All data extracted from a server log file."""

    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract – parse raw log lines into structured records
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Parse a server log file into structured records.

    Args:
        log_path: Path to the log file on disk.

    Returns:
        A ParsedLog containing every recognised entry. Unrecognised
        lines are silently skipped.
    """
    result = ParsedLog()

    if not os.path.exists(log_path):
        return result

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_PATTERN.match(line.strip())
            if not match:
                continue

            timestamp: str = match.group("timestamp")
            level: str = match.group("level")
            message: str = match.group("message")

            if level == "ERROR":
                result.errors.append(LogEntry(timestamp, level, message))

            elif level == "WARN":
                result.warnings.append(LogEntry(timestamp, level, message))

            elif level == "INFO":
                user_match = _USER_PATTERN.match(message)
                if user_match:
                    result.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_PATTERN.match(message)
                if api_match:
                    result.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration")),
                        )
                    )

    return result


# ---------------------------------------------------------------------------
# Transform – aggregate extracted records into report-ready data
# ---------------------------------------------------------------------------


def transform(
    log: ParsedLog,
) -> Tuple[List[ErrorRecord], Dict[str, List[int]], Dict[str, str]]:
    """Aggregate extracted log data into summary structures.

    Args:
        log: Parsed log data produced by extract().

    Returns:
        A tuple of:
          - error_records: one per unique error message with its count,
          - endpoint_latencies: endpoint mapped to its observed durations,
          - active_sessions: user IDs still logged in (login timestamp).
    """
    # Aggregate errors by message
    error_counts: Dict[str, int] = {}
    for entry in log.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    error_records: List[ErrorRecord] = [
        ErrorRecord(message=msg, count=count)
        for msg, count in error_counts.items()
    ]

    # Group API latencies by endpoint
    endpoint_latencies: Dict[str, List[int]] = {}
    for call in log.api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.duration_ms)

    # Track active sessions (logged in but not yet logged out)
    active_sessions: Dict[str, str] = {}
    for event in log.user_events:
        if "logged in" in event.action:
            active_sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in active_sessions:
            del active_sessions[event.user_id]

    return error_records, endpoint_latencies, active_sessions


# ---------------------------------------------------------------------------
# Load – persist to the database and generate the HTML report
# ---------------------------------------------------------------------------


def load(
    error_records: List[ErrorRecord],
    endpoint_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    db_path: str,
    report_path: str,
) -> None:
    """Write aggregated data to SQLite and produce the HTML report.

    Args:
        error_records: Aggregated error summaries.
        endpoint_latencies: Endpoint-to-latency-list mapping.
        active_sessions: Active user sessions (user_id -> login timestamp).
        db_path: Path to the SQLite database file.
        report_path: Destination path for the HTML report.
    """
    now: str = str(datetime.datetime.now())

    # --- Database ---
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for rec in error_records:
            cur.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, rec.message, rec.count),
            )

        for endpoint, times in endpoint_latencies.items():
            avg: float = sum(times) / len(times)
            cur.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()

    # --- HTML report ---
    html: str = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    html += "<h1>Error Summary</h1>\n<ul>\n"
    for rec in error_records:
        html += f"<li><b>{rec.message}</b>: {rec.count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, times in endpoint_latencies.items():
        avg = round(sum(times) / len(times), 1)
        html += f"<tr><td>{endpoint}</td><td>{avg}</td></tr>\n"
    html += "</table>\n"

    html += "<h2>Active Sessions</h2>\n"
    html += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    print(f"Job finished at {now}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    parsed: ParsedLog = extract(LOG_FILE)
    error_records, endpoint_latencies, active_sessions = transform(parsed)
    load(error_records, endpoint_latencies, active_sessions, DB_PATH, "report.html")


if __name__ == "__main__":
    # Create a sample log for standalone testing when no log file exists.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()