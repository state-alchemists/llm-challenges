import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

# Compiled regular expressions for efficient log parsing
LOG_PATTERN = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<level>[A-Z]+)\s+(?P<content>.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")
API_PATTERN = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?.*$"
)


@dataclass(frozen=True)
class ErrorLog:
    """Represents an extracted ERROR log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class WarningLog:
    """Represents an extracted WARN log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class UserEvent:
    """Represents an extracted user authentication event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiCall:
    """Represents an extracted API performance metric log entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True)
class ExtractedData:
    """Holds all raw, structured log models extracted from logs."""

    errors: List[ErrorLog]
    warnings: List[WarningLog]
    api_calls: List[ApiCall]
    user_events: List[UserEvent]


@dataclass(frozen=True)
class TransformedMetrics:
    """Holds aggregated data summaries computed during transform phase."""

    error_summary: Dict[str, int]
    api_latency_stats: Dict[str, List[int]]
    active_sessions_count: int


@dataclass(frozen=True)
class Config:
    """Environment-configured settings for paths and credentials."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_file: str


def load_config() -> Config:
    """Loads configuration settings from environment variables with safe defaults."""
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
        report_file=os.getenv("REPORT_FILE", "report.html"),
    )


def parse_user_event(dt: str, content: str, pattern: re.Pattern) -> Optional[UserEvent]:
    """Parses a user event from INFO log content."""
    match = pattern.match(content)
    if not match:
        return None
    return UserEvent(
        timestamp=dt,
        user_id=match.group("uid"),
        action=match.group("action").strip(),
    )


def parse_api_call(dt: str, content: str, pattern: re.Pattern) -> Optional[ApiCall]:
    """Parses an API call from INFO log content."""
    match = pattern.match(content)
    if not match:
        return None
    dur_str = match.group("duration")
    return ApiCall(
        timestamp=dt,
        endpoint=match.group("endpoint"),
        duration_ms=int(dur_str) if dur_str else 0,
    )


def extract_logs(file_path: str) -> ExtractedData:
    """Reads log file and extracts raw, structured log models using regex."""
    errors: List[ErrorLog] = []
    warnings: List[WarningLog] = []
    api_calls: List[ApiCall] = []
    user_events: List[UserEvent] = []

    if not os.path.exists(file_path):
        return ExtractedData(errors, warnings, api_calls, user_events)

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_PATTERN.match(line.strip())
            if not match:
                continue

            dt = match.group("dt")
            level = match.group("level")
            content = match.group("content")

            if level == "ERROR":
                errors.append(ErrorLog(timestamp=dt, message=content))
            elif level == "WARN":
                warnings.append(WarningLog(timestamp=dt, message=content))
            elif level == "INFO":
                if "User" in content:
                    event = parse_user_event(dt, content, USER_PATTERN)
                    if event is not None:
                        user_events.append(event)
                elif "API" in content:
                    call = parse_api_call(dt, content, API_PATTERN)
                    if call is not None:
                        api_calls.append(call)

    return ExtractedData(errors, warnings, api_calls, user_events)


def transform_metrics(extracted_data: ExtractedData) -> TransformedMetrics:
    """Processes the extracted raw log data into summaries and metrics."""
    error_summary: Dict[str, int] = {}
    for err in extracted_data.errors:
        error_summary[err.message] = error_summary.get(err.message, 0) + 1

    api_latency_stats: Dict[str, List[int]] = {}
    for call in extracted_data.api_calls:
        api_latency_stats.setdefault(call.endpoint, []).append(call.duration_ms)

    sessions: Dict[str, str] = {}
    for event in extracted_data.user_events:
        uid = event.user_id
        if "logged in" in event.action:
            sessions[uid] = event.timestamp
        elif "logged out" in event.action and uid in sessions:
            sessions.pop(uid)

    return TransformedMetrics(
        error_summary=error_summary,
        api_latency_stats=api_latency_stats,
        active_sessions_count=len(sessions),
    )


def load_to_database(
    db_path: str,
    metrics: TransformedMetrics,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Saves metrics to SQLite database using parameterized queries."""
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        current_time = str(datetime.datetime.now())

        for msg, count in metrics.error_summary.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)", (current_time, msg, count)
            )

        for ep, times in metrics.api_latency_stats.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (current_time, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def load_to_html_report(report_path: str, metrics: TransformedMetrics) -> None:
    """Generates and writes HTML report with the metrics."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics.api_latency_stats.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{str(round(avg, 1))}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Main function executing the ETL pipeline to process server logs."""
    config = load_config()

    extracted_data = extract_logs(config.log_file)
    metrics = transform_metrics(extracted_data)

    load_to_database(
        db_path=config.db_path,
        metrics=metrics,
        db_host=config.db_host,
        db_port=config.db_port,
        db_user=config.db_user,
    )

    load_to_html_report(config.report_file, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = load_config()
    if not os.path.exists(config.log_file):
        with open(config.log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
