"""Pipeline script for processing server logs and generating system reports.

This module extracts raw metrics from server logs, transforms them to
aggregated statistics (errors, API latency, and active sessions), and
loads them into both a database and an HTML report.
"""

from dataclasses import dataclass
import datetime
import os
from pathlib import Path
import re
import sqlite3

# Define Regex Patterns for Robust Log Parsing
LOG_LINE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Base class for parsed log entries."""

    timestamp: str
    level: str


@dataclass(frozen=True, slots=True)
class ErrorEntry(LogEntry):
    """Log entry representing an error event."""

    message: str


@dataclass(frozen=True, slots=True)
class WarnEntry(LogEntry):
    """Log entry representing a warning event."""

    message: str


@dataclass(frozen=True, slots=True)
class UserEntry(LogEntry):
    """Log entry representing user action events."""

    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEntry(LogEntry):
    """Log entry representing API latency metrics."""

    endpoint: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class ExtractedLogData:
    """Container holding lists of categorized log entries."""

    errors: list[ErrorEntry]
    warnings: list[WarnEntry]
    user_actions: list[UserEntry]
    api_calls: list[ApiEntry]


@dataclass(frozen=True, slots=True)
class TransformedMetrics:
    """Aggregated statistics derived from extracted log data."""

    error_counts: dict[str, int]
    api_latencies: dict[str, list[int]]
    active_sessions: dict[str, str]


@dataclass(frozen=True, slots=True)
class DBConfig:
    """Database connection and environment parameters."""

    path: str
    host: str
    port: int
    user: str


def parse_log_line(dt: str, lvl: str, msg: str) -> LogEntry | None:
    """Parses a log line's details into a specific LogEntry type based on level and content."""
    if lvl == "ERROR":
        return ErrorEntry(timestamp=dt, level=lvl, message=msg)
    if lvl == "WARN":
        return WarnEntry(timestamp=dt, level=lvl, message=msg)
    if lvl == "INFO":
        if user_match := USER_PATTERN.match(msg):
            uid, action = user_match.groups()
            return UserEntry(timestamp=dt, level=lvl, user_id=uid, action=action)
        if api_match := API_PATTERN.match(msg):
            endpoint, dur = api_match.groups()
            return ApiEntry(
                timestamp=dt,
                level=lvl,
                endpoint=endpoint,
                latency_ms=int(dur) if dur else 0,
            )
    return None


def extract_log_file(file_path: str) -> ExtractedLogData:
    """Reads and parses the log file using regular expressions."""
    errors: list[ErrorEntry] = []
    warnings: list[WarnEntry] = []
    user_actions: list[UserEntry] = []
    api_calls: list[ApiEntry] = []

    path = Path(file_path)
    if not path.exists():
        return ExtractedLogData(errors, warnings, user_actions, api_calls)

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not (line := line.strip()):
                continue
            if not (match := LOG_LINE_PATTERN.match(line)):
                continue

            dt, lvl, msg = match.groups()
            entry = parse_log_line(dt, lvl, msg)

            if isinstance(entry, ErrorEntry):
                errors.append(entry)
            elif isinstance(entry, WarnEntry):
                warnings.append(entry)
            elif isinstance(entry, UserEntry):
                user_actions.append(entry)
            elif isinstance(entry, ApiEntry):
                api_calls.append(entry)

    return ExtractedLogData(
        errors=errors,
        warnings=warnings,
        user_actions=user_actions,
        api_calls=api_calls,
    )


def transform_metrics(data: ExtractedLogData) -> TransformedMetrics:
    """Aggregates and transforms extracted raw log data into structured metrics."""
    error_counts: dict[str, int] = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_latencies: dict[str, list[int]] = {}
    for api in data.api_calls:
        api_latencies.setdefault(api.endpoint, []).append(api.latency_ms)

    active_sessions: dict[str, str] = {}
    for user in data.user_actions:
        if "logged in" in user.action:
            active_sessions[user.user_id] = user.timestamp
        elif "logged out" in user.action and user.user_id in active_sessions:
            active_sessions.pop(user.user_id)

    return TransformedMetrics(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=active_sessions,
    )


def load_to_database(config: DBConfig, metrics: TransformedMetrics) -> None:
    """Saves the aggregated metrics to the SQLite database."""
    print(f"Connecting to {config.host}:{config.port} as {config.user}...")

    with sqlite3.connect(config.path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in metrics.error_counts.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now_str, msg, count))

        for ep, times in metrics.api_latencies.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()


def load_to_html_report(report_path: str, metrics: TransformedMetrics) -> None:
    """Generates the HTML system report from the transformed metrics."""
    out_lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in metrics.error_counts.items():
        out_lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    out_lines.append("</ul>")

    out_lines.append("<h2>API Latency</h2>")
    out_lines.append("<table border='1'>")
    out_lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, times in metrics.api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out_lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    out_lines.append("</table>")

    out_lines.append("<h2>Active Sessions</h2>")
    out_lines.append(f"<p>{len(metrics.active_sessions)} user(s) currently active</p>")
    out_lines.append("</body>")
    out_lines.append("</html>")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))


def run_pipeline() -> None:
    """Orchestrates the log processing pipeline from end to end."""
    db_path = os.getenv("DB_PATH", "metrics.db")
    log_file = os.getenv("LOG_FILE", "server.log")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port_str = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "admin")
    report_path = os.getenv("REPORT_PATH", "report.html")

    try:
        db_port = int(db_port_str)
    except ValueError:
        db_port = 5432

    db_config = DBConfig(path=db_path, host=db_host, port=db_port, user=db_user)

    extracted_data = extract_log_file(log_file)
    metrics = transform_metrics(extracted_data)

    load_to_database(config=db_config, metrics=metrics)
    load_to_html_report(report_path=report_path, metrics=metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_file_path = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w", encoding="utf-8") as file_handle:
            file_handle.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            file_handle.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            file_handle.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            file_handle.write(
                "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            )
            file_handle.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            file_handle.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
