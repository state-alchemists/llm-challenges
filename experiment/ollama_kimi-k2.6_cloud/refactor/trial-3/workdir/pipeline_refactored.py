"""Server log ETL pipeline.

Reads structured server logs, extracts events, transforms them into aggregated
metrics, loads the results into SQLite, and writes an HTML summary report.

Configuration is read entirely from environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex patterns for log line parsing
# ---------------------------------------------------------------------------
_BASE_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|WARN|ERROR)\s+"
    r"(?P<message>.*)$"
)

_USER_PATTERN = re.compile(r"^User\s+(?P<user_id>\d+)\s+(?P<action>.+)$")
_API_PATTERN = re.compile(
    r"^API\s+(?P<endpoint>\S+)"
    r"(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PipelineConfig:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file_path: str
    report_output_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(frozen=True)
class ErrorEvent:
    """Represents an ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class UserSessionEvent:
    """Represents a user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiCallEvent:
    """Represents an API call with optional latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def load_config() -> PipelineConfig:
    """Load pipeline configuration from environment variables.

    Returns:
        PipelineConfig populated with values from the environment.
    """
    return PipelineConfig(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file_path=os.getenv("LOG_FILE_PATH", "server.log"),
        report_output_path=os.getenv("REPORT_OUTPUT_PATH", "report.html"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


def parse_log_line(line: str) -> tuple[str, str, str] | None:
    """Parse a single log line into its constituent parts.

    Args:
        line: Raw log line.

    Returns:
        A tuple of (timestamp, level, message) if the line matches the expected
        format, otherwise ``None``.
    """
    match = _BASE_LOG_PATTERN.match(line.strip())
    if not match:
        return None
    return (
        match.group("timestamp"),
        match.group("level"),
        match.group("message"),
    )


def extract_events(log_path: str) -> tuple[list[ErrorEvent], list[UserSessionEvent], list[ApiCallEvent]]:
    """Extract structured events from a server log file.

    Args:
        log_path: Path to the log file to parse.

    Returns:
        A 3-tuple of (error events, user session events, API call events).
    """
    errors: list[ErrorEvent] = []
    user_events: list[UserSessionEvent] = []
    api_calls: list[ApiCallEvent] = []

    if not Path(log_path).exists():
        return errors, user_events, api_calls

    with open(log_path, "r", encoding="utf-8") as file:
        for raw_line in file:
            parsed = parse_log_line(raw_line)
            if parsed is None:
                continue

            timestamp, level, message = parsed

            if level == "ERROR":
                errors.append(ErrorEvent(timestamp=timestamp, message=message))

            elif level == "INFO":
                user_match = _USER_PATTERN.match(message)
                if user_match:
                    user_events.append(
                        UserSessionEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_PATTERN.match(message)
                if api_match:
                    duration_str = api_match.group("duration")
                    api_calls.append(
                        ApiCallEvent(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(duration_str) if duration_str else 0,
                        )
                    )

            elif level == "WARN":
                # WARN entries are parsed but not used in downstream reporting
                # in order to preserve parity with the original pipeline.
                pass

    return errors, user_events, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def transform_error_summary(errors: list[ErrorEvent]) -> dict[str, int]:
    """Aggregate error events by message.

    Args:
        errors: List of extracted error events.

    Returns:
        Mapping of error message -> occurrence count.
    """
    summary: dict[str, int] = {}
    for event in errors:
        summary[event.message] = summary.get(event.message, 0) + 1
    return summary


def transform_api_latency(api_calls: list[ApiCallEvent]) -> dict[str, float]:
    """Compute average latency per API endpoint.

    Args:
        api_calls: List of extracted API call events.

    Returns:
        Mapping of endpoint -> average duration in milliseconds.
    """
    endpoint_times: dict[str, list[int]] = {}
    for call in api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.duration_ms)

    averages: dict[str, float] = {}
    for endpoint, times in endpoint_times.items():
        averages[endpoint] = sum(times) / len(times)
    return averages


def transform_active_sessions(user_events: list[UserSessionEvent]) -> dict[str, str]:
    """Track active sessions from a chronologically ordered list of user events.

    Args:
        user_events: List of user session events in the order they appeared
            in the log.

    Returns:
        Mapping of user_id -> most recent login timestamp for users that
        are currently logged in.
    """
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def init_database(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and ensure required tables exist.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open SQLite connection with the required schema in place.
    """
    conn = sqlite3.connect(db_path)
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
    return conn


def load_error_metrics(
    conn: sqlite3.Connection, error_summary: dict[str, int]
) -> None:
    """Insert aggregated error metrics into the database.

    Args:
        conn: Active SQLite connection.
        error_summary: Mapping of error message -> count.
    """
    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    cursor = conn.cursor()
    for message, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )
    conn.commit()


def load_api_metrics(
    conn: sqlite3.Connection, api_latency: dict[str, float]
) -> None:
    """Insert aggregated API latency metrics into the database.

    Args:
        conn: Active SQLite connection.
        api_latency: Mapping of endpoint -> average latency in milliseconds.
    """
    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    cursor = conn.cursor()
    for endpoint, avg_ms in api_latency.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )
    conn.commit()


def generate_report_html(
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_session_count: int,
) -> str:
    """Generate an HTML report string.

    Args:
        error_summary: Mapping of error message -> occurrence count.
        api_latency: Mapping of endpoint -> average latency in milliseconds.
        active_session_count: Number of currently active user sessions.

    Returns:
        HTML document as a string.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_summary.items():
        lines.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>"
        )
    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    for endpoint, avg_ms in api_latency.items():
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines)


def write_report(report_path: str, html: str) -> None:
    """Write the HTML report to disk.

    Args:
        report_path: Destination file path.
        html: HTML content to write.
    """
    Path(report_path).write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def main() -> None:
    """Orchestrate the Extract → Transform → Load pipeline."""
    config = load_config()

    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )

    # Extract
    errors, user_events, api_calls = extract_events(config.log_file_path)

    # Transform
    error_summary = transform_error_summary(errors)
    api_latency = transform_api_latency(api_calls)
    active_sessions = transform_active_sessions(user_events)

    # Load to database
    conn = init_database(config.db_path)
    try:
        load_error_metrics(conn, error_summary)
        load_api_metrics(conn, api_latency)
    finally:
        conn.close()

    # Generate and write report
    html = generate_report_html(
        error_summary, api_latency, len(active_sessions)
    )
    write_report(config.report_output_path, html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create sample data if the log file does not exist so the script remains
    # self-contained for demonstration purposes.
    log_path = os.getenv("LOG_FILE_PATH", "server.log")
    if not Path(log_path).exists():
        Path(log_path).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    main()
