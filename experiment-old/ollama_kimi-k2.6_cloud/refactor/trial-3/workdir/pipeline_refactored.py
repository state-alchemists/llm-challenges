"""Server log ETL pipeline: extract, transform, and load log data into SQLite and HTML."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration (loaded from environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorRecord:
    """An error or warning log entry."""
    timestamp: str
    message: str
    level: str


@dataclass(frozen=True)
class UserRecord:
    """A user session event log entry."""
    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiRecord:
    """An API latency log entry."""
    timestamp: str
    endpoint: str
    duration_ms: int


LogRecord = ErrorRecord | UserRecord | ApiRecord


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
)
_USER_RE = re.compile(r"^User (\d+) (.+)$")
_API_RE = re.compile(r"^API (\S+) took (\d+)ms$")


def parse_log_line(line: str) -> Optional[LogRecord]:
    """Parse a single log line into a typed record.

    Args:
        line: Raw text line from the log file.

    Returns:
        A typed log record, or None if the line does not match.
    """
    match = _LOG_LINE_RE.match(line)
    if not match:
        return None

    timestamp, level, remainder = match.groups()

    if level in ("ERROR", "WARN"):
        return ErrorRecord(timestamp=timestamp, message=remainder, level=level)

    if level == "INFO":
        user_match = _USER_RE.match(remainder)
        if user_match:
            user_id, action = user_match.groups()
            return UserRecord(timestamp=timestamp, user_id=user_id, action=action)

        api_match = _API_RE.match(remainder)
        if api_match:
            endpoint, duration = api_match.groups()
            return ApiRecord(timestamp=timestamp, endpoint=endpoint, duration_ms=int(duration))

    return None


def extract_logs(log_path: str) -> List[LogRecord]:
    """Read and parse all valid records from a log file.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of parsed log records.
    """
    records: List[LogRecord] = []
    path = Path(log_path)
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = parse_log_line(line)
            if record is not None:
                records.append(record)

    return records


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_data(records: List[LogRecord]) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Aggregate extracted records into summary statistics.

    Args:
        records: Parsed log records from the extraction step.

    Returns:
        A tuple of:
        - error_counts: Mapping of error/warning message to occurrence count.
        - api_latencies: Mapping of endpoint to list of response times.
        - active_sessions: Mapping of user_id to login timestamp.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for record in records:
        if isinstance(record, ErrorRecord):
            error_counts[record.message] = error_counts.get(record.message, 0) + 1

        elif isinstance(record, UserRecord):
            if "logged in" in record.action:
                active_sessions[record.user_id] = record.timestamp
            elif "logged out" in record.action and record.user_id in active_sessions:
                active_sessions.pop(record.user_id)

        elif isinstance(record, ApiRecord):
            api_latencies.setdefault(record.endpoint, []).append(record.duration_ms)

    return error_counts, api_latencies, active_sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Aggregated error/warning counts.
        api_latencies: Aggregated API response times by endpoint.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for message, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> str:
    """Generate an HTML report from transformed metrics.

    Args:
        error_counts: Aggregated error/warning counts.
        api_latencies: Aggregated API response times by endpoint.
        active_sessions: Currently active user sessions.

    Returns:
        Complete HTML document as a string.
    """
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

    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def write_report(report_html: str, output_path: str = "report.html") -> None:
    """Write the HTML report to disk.

    Args:
        report_html: HTML content to write.
        output_path: Destination file path.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    records = extract_logs(LOG_FILE)
    error_counts, api_latencies, active_sessions = transform_data(records)
    load_to_database(DB_PATH, error_counts, api_latencies)
    report = generate_html_report(error_counts, api_latencies, active_sessions)
    write_report(report)

    print(f"Job finished at {datetime.datetime.now()}")


def seed_test_data() -> None:
    """Create a sample log file if one does not already exist."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


if __name__ == "__main__":
    seed_test_data()
    main()
