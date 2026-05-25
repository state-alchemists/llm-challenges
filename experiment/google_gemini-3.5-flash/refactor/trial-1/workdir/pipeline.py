"""Pipeline script to process server logs, extract metrics, and load them to SQLite database and HTML report."""

from dataclasses import dataclass
import datetime
import os
import re
import sqlite3
from typing import Dict, List


@dataclass
class ErrorEvent:
    """Represents a single parsed log line of severity ERROR."""

    dt: str
    message: str


@dataclass
class ApiEvent:
    """Represents a single parsed API performance log line."""

    dt: str
    endpoint: str
    latency_ms: int


@dataclass
class UserEvent:
    """Represents a parsed user login/logout activity log line."""

    dt: str
    uid: str
    action: str


@dataclass
class LogData:
    """Holds all extracted lists of events from the server log."""

    errors: List[ErrorEvent]
    api_calls: List[ApiEvent]
    user_events: List[UserEvent]


@dataclass
class TransformedMetrics:
    """Contains transformed, aggregated metrics from log entries."""

    error_summary: Dict[str, int]
    api_latency_stats: Dict[str, float]
    active_sessions_count: int


def extract_log_data(log_file_path: str) -> LogData:
    """Extract raw event data from the server log file using regex.

    Args:
        log_file_path: Path to the log file to be read.

    Returns:
        A LogData object containing lists of parsed errors, API calls, and user events.
    """
    errors: List[ErrorEvent] = []
    api_calls: List[ApiEvent] = []
    user_events: List[UserEvent] = []

    if not os.path.exists(log_file_path):
        return LogData(errors=errors, api_calls=api_calls, user_events=user_events)

    # Patterns for regex-based parsing
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
    )
    user_pattern = re.compile(r"^User (\S+) (.*)$")
    api_pattern = re.compile(r"^API (\S+)(?: took (\d+)ms)?.*$")

    with open(log_file_path, "r", encoding="utf-8") as file:
        for line in file:
            match = log_pattern.match(line)
            if not match:
                continue

            dt, level, content = match.groups()

            if level == "ERROR":
                errors.append(ErrorEvent(dt=dt, message=content.strip()))
            elif level == "INFO":
                user_match = user_pattern.match(content)
                if user_match:
                    uid, action = user_match.groups()
                    user_events.append(UserEvent(dt=dt, uid=uid, action=action.strip()))
                else:
                    api_match = api_pattern.match(content)
                    if api_match:
                        endpoint, raw_ms = api_match.groups()
                        latency = int(raw_ms) if raw_ms is not None else 0
                        api_calls.append(
                            ApiEvent(dt=dt, endpoint=endpoint, latency_ms=latency)
                        )

    return LogData(errors=errors, api_calls=api_calls, user_events=user_events)


def transform_log_data(log_data: LogData) -> TransformedMetrics:
    """Transform extracted log data into aggregated metrics.

    Args:
        log_data: The extracted LogData containing events.

    Returns:
        TransformedMetrics containing structured summary stats.
    """
    # 1. Error Summary
    error_summary: Dict[str, int] = {}
    for error in log_data.errors:
        error_summary[error.message] = error_summary.get(error.message, 0) + 1

    # 2. API Latency Statistics
    api_durations: Dict[str, List[int]] = {}
    for call in log_data.api_calls:
        api_durations.setdefault(call.endpoint, []).append(call.latency_ms)

    api_latency_stats: Dict[str, float] = {}
    for endpoint, times in api_durations.items():
        if times:
            api_latency_stats[endpoint] = sum(times) / len(times)
        else:
            api_latency_stats[endpoint] = 0.0

    # 3. Active Sessions Count
    sessions: Dict[str, str] = {}
    for event in log_data.user_events:
        if "logged in" in event.action:
            sessions[event.uid] = event.dt
        elif "logged out" in event.action:
            sessions.pop(event.uid, None)

    return TransformedMetrics(
        error_summary=error_summary,
        api_latency_stats=api_latency_stats,
        active_sessions_count=len(sessions),
    )


def load_data(
    metrics: TransformedMetrics,
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Load transformed metrics into the database.

    Args:
        metrics: The transformed metrics.
        db_path: The SQLite database file path.
        db_host: Database host (for logging/printing).
        db_port: Database port (for logging/printing).
        db_user: Database user (for logging/printing).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    current_time = str(datetime.datetime.now())

    for msg, count in metrics.error_summary.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (current_time, msg, count),
        )

    for ep, avg in metrics.api_latency_stats.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (current_time, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(metrics: TransformedMetrics, report_path: str) -> None:
    """Generate HTML report from transformed metrics.

    Args:
        metrics: The transformed metrics.
        report_path: Path where the HTML report will be written.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.api_latency_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as file:
        file.write(out)


if __name__ == "__main__":
    # Ensure config options are retrieved from environment variables with sensible defaults
    log_file_path = os.getenv("LOG_FILE", "server.log")
    db_path = os.getenv("DB_PATH", "metrics.db")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "admin")
    db_pass = os.getenv("DB_PASS", "password123")

    if not os.path.exists(log_file_path):
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Run the ETL pipeline
    log_data = extract_log_data(log_file_path)
    metrics = transform_log_data(log_data)
    load_data(metrics, db_path, db_host, db_port, db_user)
    generate_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")
