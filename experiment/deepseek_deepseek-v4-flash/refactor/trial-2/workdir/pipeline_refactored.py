"""Refactored server-log pipeline: extract, transform, load, report.

All configuration comes from environment variables (``DB_PATH``, ``LOG_FILE``,
``REPORT_PATH``, ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASS``) instead of
hardcoded constants. Log lines are parsed with regular expressions, database
writes use parameterized queries, and the work is split into well-named
functions following the Extract -> Transform -> Load pattern.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration read from environment variables."""

    db_path: str
    log_file: str
    report_path: str
    db_host: str
    db_port: str
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read all configuration from environment variables, with local defaults."""
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        report_path=os.getenv("REPORT_PATH", "report.html"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=os.getenv("DB_PORT", "5432"),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def ensure_log_file(log_path: str) -> None:
    """Create a sample log file when none exists yet (developer convenience)."""
    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as file:
            file.write(SAMPLE_LOG)


def extract_log_lines(log_path: str) -> list[str]:
    """Read the log file and return each line with its trailing newline removed."""
    with open(log_path, "r", encoding="utf-8") as file:
        return [line.rstrip("\n") for line in file]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\S+\s+\S+)\s+(?P<level>ERROR|INFO|WARN)\s+(?P<message>.+)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms?)?$")


@dataclass(frozen=True)
class LogRecord:
    """A parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass(frozen=True)
class UserEvent:
    """A parsed user activity line (login/logout)."""

    uid: str
    action: str


@dataclass(frozen=True)
class ApiEvent:
    """A parsed API latency line."""

    endpoint: str
    duration_ms: int


def parse_log_line(line: str) -> LogRecord | None:
    """Parse one log line, or return ``None`` for unparseable/ignored lines."""
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None
    return LogRecord(
        timestamp=match.group("timestamp"),
        level=match.group("level"),
        message=match.group("message").strip(),
    )


def parse_user_message(message: str) -> UserEvent | None:
    """Parse the payload of an ``INFO User <uid> <action>`` line."""
    match = _USER_RE.match(message)
    if match is None:
        return None
    return UserEvent(uid=match.group("uid"), action=match.group("action").strip())


def parse_api_message(message: str) -> ApiEvent | None:
    """Parse the payload of an ``INFO API <endpoint> took <ms>ms`` line."""
    match = _API_RE.match(message)
    if match is None:
        return None
    duration = match.group("duration")
    return ApiEvent(
        endpoint=match.group("endpoint"),
        duration_ms=int(duration) if duration is not None else 0,
    )


@dataclass(frozen=True)
class ReportData:
    """Aggregated metrics backing both the database load and the report."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_sessions: int


def transform_logs(lines: list[str]) -> ReportData:
    """Aggregate raw log lines into error counts, API latencies, and sessions."""
    error_counts: dict[str, int] = {}
    endpoint_times: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for line in lines:
        record = parse_log_line(line)
        if record is None:
            continue
        if record.level == "ERROR":
            message = record.message
            error_counts[message] = error_counts.get(message, 0) + 1
        elif record.level == "INFO" and record.message.startswith("User "):
            event = parse_user_message(record.message)
            if event is None:
                continue
            if "logged in" in event.action:
                sessions[event.uid] = record.timestamp
            elif "logged out" in event.action:
                sessions.pop(event.uid, None)
        elif record.level == "INFO" and record.message.startswith("API "):
            event = parse_api_message(record.message)
            if event is None:
                continue
            endpoint_times.setdefault(event.endpoint, []).append(event.duration_ms)
        # WARN records are parsed but do not contribute to the report.

    endpoint_avg_ms = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }
    return ReportData(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(config: Config, data: ReportData) -> None:
    """Persist error counts and API latency averages into the SQLite database."""
    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now = str(datetime.datetime.now())
        for message, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, avg_ms in data.endpoint_avg_ms.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(data: ReportData) -> str:
    """Build the HTML report: error summary, API latency table, session count."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for message, count in data.error_counts.items():
        out += f"<li><b>{message}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, avg_ms in data.endpoint_avg_ms.items():
        out += f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>\n"
    out += "</table>\n"
    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{data.active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out


def write_report(report_path: str, html: str) -> None:
    """Write the generated HTML report to disk."""
    with open(report_path, "w", encoding="utf-8") as file:
        file.write(html)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full pipeline: extract, transform, load, and report."""
    config = load_config()
    ensure_log_file(config.log_file)
    lines = extract_log_lines(config.log_file)
    data = transform_logs(lines)
    load_to_db(config, data)
    html = render_report(data)
    write_report(config.report_path, html)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    main()
