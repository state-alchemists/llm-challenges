"""A clean, secure, and maintainable ETL pipeline for server logs.

This script processes server logs, computes analytical summaries, stores the
metrics in an SQLite database, and generates an HTML report. All configuration
is done via environment variables.
"""

from dataclasses import dataclass
import datetime
import os
from pathlib import Path
import re
import sqlite3

# --- Configuration (Requirement 1) ---
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# --- Data Models (Requirement 5) ---
@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Represents a parsed error log event."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class WarnEvent:
    """Represents a parsed warning log event."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserSessionEvent:
    """Represents a parsed user login or logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCallEvent:
    """Represents a parsed API call latency event."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ExtractedData:
    """Holds all extracted raw events categorized by type."""

    errors: list[ErrorEvent]
    warnings: list[WarnEvent]
    user_sessions: list[UserSessionEvent]
    api_calls: list[ApiCallEvent]


@dataclass(frozen=True, slots=True)
class TransformedData:
    """Holds metrics computed from raw log events."""

    error_counts: dict[str, int]
    api_latencies: dict[str, list[int]]
    active_sessions: dict[str, str]


# --- Regular Expressions for Parsing (Requirement 4) ---
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


# --- Helper Parsing Functions ---
def _parse_info_payload(
    timestamp: str, payload: str
) -> UserSessionEvent | ApiCallEvent | None:
    """Parses the payload of an INFO log level into specific events."""
    if user_match := USER_PATTERN.match(payload):
        user_id, action = user_match.groups()
        return UserSessionEvent(timestamp=timestamp, user_id=user_id, action=action)

    if api_match := API_PATTERN.match(payload):
        endpoint, duration_str = api_match.groups()
        duration_ms = int(duration_str) if duration_str is not None else 0
        return ApiCallEvent(
            timestamp=timestamp, endpoint=endpoint, duration_ms=duration_ms
        )

    return None


def parse_log_line(
    line: str,
) -> ErrorEvent | WarnEvent | UserSessionEvent | ApiCallEvent | None:
    """Parses a single log line into a structured event using regular expressions."""
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    timestamp, level, payload = match.groups()

    if level == "ERROR":
        return ErrorEvent(timestamp=timestamp, message=payload)
    if level == "WARN":
        return WarnEvent(timestamp=timestamp, message=payload)
    if level == "INFO":
        return _parse_info_payload(timestamp, payload)

    return None


# --- Extract (Requirement 3) ---
def extract_logs(file_path: str) -> ExtractedData:
    """Reads and parses log lines from the specified file path."""
    errors: list[ErrorEvent] = []
    warnings: list[WarnEvent] = []
    user_sessions: list[UserSessionEvent] = []
    api_calls: list[ApiCallEvent] = []

    path = Path(file_path)
    if not path.exists():
        return ExtractedData(errors, warnings, user_sessions, api_calls)

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if event := parse_log_line(line):
                if isinstance(event, ErrorEvent):
                    errors.append(event)
                elif isinstance(event, WarnEvent):
                    warnings.append(event)
                elif isinstance(event, UserSessionEvent):
                    user_sessions.append(event)
                elif isinstance(event, ApiCallEvent):
                    api_calls.append(event)

    return ExtractedData(
        errors=errors,
        warnings=warnings,
        user_sessions=user_sessions,
        api_calls=api_calls,
    )


# --- Transform (Requirement 3) ---
def transform_data(extracted: ExtractedData) -> TransformedData:
    """Processes extracted raw log events to compute analytical metrics."""
    error_counts: dict[str, int] = {}
    for error in extracted.errors:
        error_counts[error.message] = error_counts.get(error.message, 0) + 1

    api_latencies: dict[str, list[int]] = {}
    for api_call in extracted.api_calls:
        api_latencies.setdefault(api_call.endpoint, []).append(api_call.duration_ms)

    active_sessions: dict[str, str] = {}
    for session in extracted.user_sessions:
        if "logged in" in session.action:
            active_sessions[session.user_id] = session.timestamp
        elif "logged out" in session.action and session.user_id in active_sessions:
            active_sessions.pop(session.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=active_sessions,
    )


# --- Load Helpers & DB Initializer ---
def _init_db(cursor: sqlite3.Cursor) -> None:
    """Creates database tables if they do not exist."""
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


# --- Load (Requirement 3) ---
def load_to_database(
    transformed: TransformedData,
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Inserts computed metrics into the SQLite database securely (Requirement 2)."""
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        _init_db(c)
        now = datetime.datetime.now()

        for msg, count in transformed.error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (str(now), msg, count),
            )

        for ep, times in transformed.api_latencies.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (str(now), ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report_html(transformed: TransformedData, output_path: str) -> None:
    """Generates an HTML system report from the processed metrics."""
    errors_html = "".join(
        f"<li><b>{m}</b>: {c} occurrences</li>\n"
        for m, c in transformed.error_counts.items()
    )
    api_html = "".join(
        f"<tr><td>{ep}</td><td>{round(sum(ts)/len(ts), 1)}</td></tr>\n"
        for ep, ts in transformed.api_latencies.items()
        if ts
    )
    session_count = len(transformed.active_sessions)

    out = (
        f"<html>\n<head><title>System Report</title></head>\n<body>\n"
        f"<h1>Error Summary</h1>\n<ul>\n{errors_html}</ul>\n"
        f"<h2>API Latency</h2>\n<table border='1'>\n"
        f"<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n{api_html}</table>\n"
        f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
        f"</body>\n</html>"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline(
    log_file: str = LOG_FILE,
    db_path: str = DB_PATH,
    db_host: str = DB_HOST,
    db_port: int = DB_PORT,
    db_user: str = DB_USER,
) -> None:
    """Runs the complete ETL pipeline."""
    extracted = extract_logs(log_file)
    transformed = transform_data(extracted)
    load_to_database(
        transformed=transformed,
        db_path=db_path,
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
    )
    generate_report_html(transformed, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_log:
            f_log.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_log.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_log.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_log.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
