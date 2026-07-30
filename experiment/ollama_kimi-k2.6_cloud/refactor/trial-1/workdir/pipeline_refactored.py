"""Refactored pipeline for processing server logs and generating reports.

Follows an ETL pattern:
    Extract   -> read and parse server.log with regex
    Transform -> aggregate errors, API latencies, and active sessions
    Load      -> insert aggregated metrics into SQLite via parameterized queries
    Report    -> emit report.html

All configuration is read from environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Configuration (read from environment variables)
# ---------------------------------------------------------------------------

def _getenv_int(key: str, default: int) -> int:
    """Return an environment variable as an int, or a default."""
    val = os.getenv(key)
    return int(val) if val is not None else default


LOG_FILE = os.getenv("LOG_FILE_PATH", "server.log")
DB_PATH = os.getenv("DB_PATH", "metrics.db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _getenv_int("DB_PORT", 5432)
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_PATH = os.getenv("REPORT_PATH", "report.html")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorEntry:
    """Represents an ERROR line from the log."""
    timestamp: str
    message: str


@dataclass(frozen=True)
class ApiEntry:
    """Represents an INFO … API … line from the log."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True)
class UserEntry:
    """Represents an INFO … User … line from the log."""
    timestamp: str
    user_id: str
    action: str


LogEntry = Union[ErrorEntry, ApiEntry, UserEntry]


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Primary log line matcher: <timestamp> <level> <message…>
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)

# User activity matcher: User <id> <action…>
_USER_RE = re.compile(r"^User\s+(\d+)\s+(.+)$")

# API call matcher: API <endpoint> [took <duration>ms]
_API_RE = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse a single log line into a strongly-typed entry using regex.

    Returns *None* for empty lines, malformed lines, or levels that are
    not part of the reporting surface (e.g. WARN — parsed by the legacy
    script but never consumed).
    """
    line = line.strip()
    if not line:
        return None

    match = _LOG_LINE_RE.match(line)
    if not match:
        return None

    timestamp, level, message = match.groups()

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, message=message.strip())

    if level == "WARN":
        # Legacy code parsed WARN but never surfaced it in the DB or report.
        return None

    if level == "INFO":
        user_match = _USER_RE.match(message)
        if user_match:
            user_id, action = user_match.groups()
            return UserEntry(
                timestamp=timestamp, user_id=user_id, action=action.strip()
            )

        api_match = _API_RE.match(message)
        if api_match:
            endpoint = api_match.group(1)
            dur_str = api_match.group(2)
            duration_ms = int(dur_str) if dur_str is not None else 0
            return ApiEntry(
                timestamp=timestamp, endpoint=endpoint, duration_ms=duration_ms
            )

    return None


def extract(log_file_path: str) -> List[LogEntry]:
    """Read *log_file_path* and return a list of parsed, typed log entries."""
    entries: List[LogEntry] = []
    if not os.path.exists(log_file_path):
        return entries

    with open(log_file_path, "r", encoding="utf-8") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Aggregate parsed entries into metrics.

    Returns:
        - error_counts: mapping of error message -> occurrence count
        - api_latencies: mapping of endpoint -> list of durations (ms)
        - active_session_count: number of users currently logged in
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, ApiEntry):
            api_latencies.setdefault(entry.endpoint, []).append(entry.duration_ms)

        elif isinstance(entry, UserEntry):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)

    return error_counts, api_latencies, len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Load aggregated metrics into SQLite using parameterized queries.

    NOTE: DB_HOST, DB_PORT, DB_USER, and DB_PASS are read from the environment
    for parity with the legacy script, but SQLite only requires a file path.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat()

        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in api_latencies.items():
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_session_count: int,
    output_path: str,
) -> None:
    """Generate *output_path* (HTML) containing the error summary, API latency
    table, and active session count."""
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

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Bootstrap / Main
# ---------------------------------------------------------------------------

def _create_sample_log(log_file_path: str) -> None:
    """Seed a sample *server.log* if one does not already exist."""
    if os.path.exists(log_file_path):
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(log_file_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines) + "\n")


def main() -> None:
    """Orchestrate the ETL pipeline."""
    _create_sample_log(LOG_FILE)

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    entries = extract(LOG_FILE)
    error_counts, api_latencies, active_session_count = transform(entries)
    load_to_database(DB_PATH, error_counts, api_latencies)
    generate_report(error_counts, api_latencies, active_session_count, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
