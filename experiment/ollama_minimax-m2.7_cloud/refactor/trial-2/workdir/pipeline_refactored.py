"""
Log processing pipeline that extracts metrics from server logs and generates an HTML report.

Architecture follows an ETL pattern:
    Extract   - parse raw log lines into structured entries
    Transform - aggregate entries into error summaries, API metrics, and session counts
    Load      - write to SQLite and produce the HTML report

Configuration is read from environment variables (see CONFIG_DEFAULTS).
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Literal, Optional

# UTC helper — always use timezone-aware UTC datetimes
_utcnow = lambda: datetime.datetime.now(datetime.timezone.utc)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str | None = None
LOG_FILE_PATH: str | None = None
DB_HOST: str | None = None
DB_PORT: str | None = None
DB_USER: str | None = None
DB_PASS: str | None = None


def _get_config() -> dict[str, str]:
    """Load configuration from environment variables with fallback defaults."""
    return {
        "db_path": os.environ.get("PIPELINE_DB_PATH", "metrics.db"),
        "log_file": os.environ.get("PIPELINE_LOG_FILE", "server.log"),
        "db_host": os.environ.get("PIPELINE_DB_HOST", "localhost"),
        "db_port": os.environ.get("PIPELINE_DB_PORT", "5432"),
        "db_user": os.environ.get("PIPELINE_DB_USER", "admin"),
        "db_pass": os.environ.get("PIPELINE_DB_PASS", ""),
    }


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

LogEntryType = Literal["ERR", "USR", "API", "WARN"]


@dataclass
class LogEntry:
    """
    Structured representation of a single parsed log line.

    Attributes
    ----------
    timestamp : str
        Formatted as 'YYYY-MM-DD HH:MM:SS'.
    level : str
        One of ERROR, WARN, INFO.
    entry_type : LogEntryType | None
        Internal classification used by the pipeline (ERR, USR, API, WARN).
    message : str | None
        Raw message body; used for errors and warnings.
    user_id : str | None
        User identifier extracted from user activity lines.
    action : str | None
        Human-readable action from user activity lines (e.g. 'logged in').
    endpoint : str | None
        API endpoint path (e.g. '/users/profile').
    duration_ms : int | None
        API call duration in milliseconds.
    """

    timestamp: str
    level: str
    entry_type: LogEntryType | None = None
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches: 2024-01-01 12:00:00 INFO User 42 logged in
USER_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO) "
    r"User (?P<user_id>\S+) (?P<action>logged in|logged out)$"
)

# Matches: 2024-01-01 12:05:00 ERROR Database timeout
ERROR_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR) "
    r"(?P<message>.+)$"
)

# Matches: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
API_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO) "
    r"API (?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)

# Matches: 2024-01-01 12:09:00 WARN Memory usage at 87%
WARN_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>WARN) "
    r"(?P<message>.+)$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> LogEntry | None:
    """
    Parse a single log line into a LogEntry.

    Attempts to match the line against each known pattern in order.
    Returns None if the line does not match any pattern.

    Parameters
    ----------
    line : str
        A single raw log line (no trailing newline).

    Returns
    -------
    LogEntry | None
        Structured entry, or None if the line is unrecognised.
    """
    line = line.rstrip("\n")

    # Try API first (most specific)
    m = API_PATTERN.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level=m.group("level"),
            entry_type="API",
            endpoint=m.group("endpoint"),
            duration_ms=int(m.group("duration")),
        )

    # Try user activity
    m = USER_PATTERN.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level=m.group("level"),
            entry_type="USR",
            user_id=m.group("user_id"),
            action=m.group("action"),
        )

    # Try error
    m = ERROR_PATTERN.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level=m.group("level"),
            entry_type="ERR",
            message=m.group("message"),
        )

    # Try warning
    m = WARN_PATTERN.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level=m.group("level"),
            entry_type="WARN",
            message=m.group("message"),
        )

    return None


def extract_log_entries(log_file_path: str) -> list[LogEntry]:
    """
    Read a log file and return all parsed LogEntry objects.

    Parameters
    ----------
    log_file_path : str
        Path to the server log file.

    Returns
    -------
    list[LogEntry]
        Entries in the order they appear in the file.
    """
    entries: list[LogEntry] = []
    if not os.path.exists(log_file_path):
        return entries

    with open(log_file_path, "r") as fh:
        for raw_line in fh:
            entry = parse_log_line(raw_line)
            if entry is not None:
                entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_to_error_counts(entries: list[LogEntry]) -> dict[str, int]:
    """
    Aggregate ERROR entries by message text.

    Parameters
    ----------
    entries : list[LogEntry]
        All log entries.

    Returns
    -------
    dict[str, int]
        Mapping from error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.entry_type == "ERR" and entry.message is not None:
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def transform_to_api_metrics(
    entries: list[LogEntry],
) -> dict[str, list[int]]:
    """
    Group API call durations by endpoint.

    Parameters
    ----------
    entries : list[LogEntry]
        All log entries.

    Returns
    -------
    dict[str, list[int]]
        Mapping from endpoint path to a list of observed durations in ms.
    """
    metrics: dict[str, list[int]] = {}
    for entry in entries:
        if entry.entry_type == "API" and entry.endpoint is not None:
            metrics.setdefault(entry.endpoint, []).append(entry.duration_ms or 0)
    return metrics


def transform_to_active_sessions(entries: list[LogEntry]) -> set[str]:
    """
    Determine which users are currently active based on login/logout events.

    A user is considered active if they have logged in and have not yet
    logged out. The final set reflects session state after processing
    the entire log in chronological order.

    Parameters
    ----------
    entries : list[LogEntry]
        All log entries in chronological order.

    Returns
    -------
    set[str]
        Set of currently-active user IDs.
    """
    active: set[str] = set()
    for entry in entries:
        if entry.entry_type == "USR" and entry.user_id is not None:
            if entry.action == "logged in":
                active.add(entry.user_id)
            elif entry.action == "logged out":
                active.discard(entry.user_id)
    return active


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create tables for errors and API metrics if they do not already exist.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_errors_to_db(
    conn: sqlite3.Connection,
    errors: dict[str, int],
    timestamp: str | None = None,
) -> None:
    """
    Insert aggregated error counts into the errors table.

    Uses a parameterised query to prevent SQL injection.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    errors : dict[str, int]
        Mapping from error message to count.
    timestamp : str | None
        Override timestamp string; defaults to the current UTC time.
    """
    ts = timestamp or _utcnow().isoformat()
    for msg, count in errors.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (ts, msg, count),
        )


def load_api_metrics_to_db(
    conn: sqlite3.Connection,
    metrics: dict[str, list[int]],
    timestamp: str | None = None,
) -> None:
    """
    Compute average latency per endpoint and insert into api_metrics table.

    Uses a parameterised query to prevent SQL injection.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    metrics : dict[str, list[int]]
        Mapping from endpoint to list of observed durations in ms.
    timestamp : str | None
        Override timestamp string; defaults to the current UTC time.
    """
    ts = timestamp or _utcnow().isoformat()
    for endpoint, durations in metrics.items():
        avg_ms = sum(durations) / len(durations)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (ts, endpoint, avg_ms),
        )


def generate_html_report(
    errors: dict[str, int],
    api_metrics: dict[str, list[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Write the HTML report covering errors, API latency, and active sessions.

    Parameters
    ----------
    errors : dict[str, int]
        Error message counts.
    api_metrics : dict[str, list[int]]
        Endpoint to list of durations in ms.
    active_sessions : int
        Number of currently active users.
    output_path : str
        Destination file path for the HTML report.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in errors.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, durations in api_metrics.items():
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Execute the full ETL pipeline.

    Configuration is read from environment variables (see CONFIG_DEFAULTS).
    Produces ``metrics.db`` and ``report.html`` in the working directory.
    """
    cfg = _get_config()

    print(
        f"Connecting to {cfg['db_host']}:{cfg['db_port']} as {cfg['db_user']}..."
    )

    # Extract
    entries = extract_log_entries(cfg["log_file"])

    # Transform
    errors = transform_to_error_counts(entries)
    api_metrics = transform_to_api_metrics(entries)
    active_sessions = transform_to_active_sessions(entries)

    # Load — database
    conn = sqlite3.connect(cfg["db_path"])
    try:
        init_db(conn)
        load_errors_to_db(conn, errors)
        load_api_metrics_to_db(conn, api_metrics)
        conn.commit()
    finally:
        conn.close()

    # Load — report
    generate_html_report(errors, api_metrics, len(active_sessions), "report.html")

    print(f"Job finished at {_utcnow().isoformat()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Seed a default log file so the script runs standalone.
    cfg = _get_config()
    if not os.path.exists(cfg["log_file"]):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(cfg["log_file"], "w") as fh:
            fh.write("\n".join(sample_lines) + "\n")

    run_pipeline()
