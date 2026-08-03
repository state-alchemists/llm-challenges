#!/usr/bin/env python3
"""Refactored log processing and reporting pipeline.

Provides a clean, modular, parameterized, and secure pipeline following
the Extract-Transform-Load (ETL) pattern.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass

# --- Regular Expressions for parsing ---
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<message>.*)$"
)
USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.*)$")
API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?")


@dataclass(frozen=True, slots=True)
class ErrorLog:
    """Represents a parsed error log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserLog:
    """Represents a parsed user session log entry."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiLog:
    """Represents a parsed API latency log entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnLog:
    """Represents a parsed warning log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class ExtractedData:
    """Container for raw extracted log data."""

    errors: list[ErrorLog]
    user_logs: list[UserLog]
    api_logs: list[ApiLog]
    warn_logs: list[WarnLog]


@dataclass(frozen=True, slots=True)
class TransformedMetrics:
    """Container for aggregated pipeline metrics."""

    error_counts: dict[str, int]
    api_averages: dict[str, float]
    active_sessions: dict[str, str]


def extract(log_file_path: str) -> ExtractedData:
    """Extracts structured log entries from the specified log file.

    If the log file does not exist, returns an empty ExtractedData container.
    """
    errors: list[ErrorLog] = []
    user_logs: list[UserLog] = []
    api_logs: list[ApiLog] = []
    warn_logs: list[WarnLog] = []

    if not os.path.exists(log_file_path):
        return ExtractedData(errors, user_logs, api_logs, warn_logs)

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            dt = match.group("timestamp")
            lvl = match.group("level")
            msg = match.group("message")

            if lvl == "ERROR":
                errors.append(ErrorLog(timestamp=dt, message=msg))
            elif lvl == "INFO":
                user_match = USER_RE.match(msg)
                if user_match:
                    user_id = user_match.group("user_id")
                    action = user_match.group("action").strip()
                    user_logs.append(
                        UserLog(timestamp=dt, user_id=user_id, action=action)
                    )
                else:
                    api_match = API_RE.match(msg)
                    if api_match:
                        endpoint = api_match.group("endpoint")
                        dur_str = api_match.group("duration")
                        dur = int(dur_str) if dur_str else 0
                        api_logs.append(
                            ApiLog(timestamp=dt, endpoint=endpoint, duration_ms=dur)
                        )
            elif lvl == "WARN":
                warn_logs.append(WarnLog(timestamp=dt, message=msg))

    return ExtractedData(
        errors=errors,
        user_logs=user_logs,
        api_logs=api_logs,
        warn_logs=warn_logs,
    )


def transform(extracted: ExtractedData) -> TransformedMetrics:
    """Transforms raw extracted log data into aggregated pipeline metrics."""
    # Count error occurrences
    error_counts: dict[str, int] = {}
    for error in extracted.errors:
        error_counts[error.message] = error_counts.get(error.message, 0) + 1

    # Track user sessions sequentially to capture logins and logouts
    active_sessions: dict[str, str] = {}
    for user_log in extracted.user_logs:
        if "logged in" in user_log.action:
            active_sessions[user_log.user_id] = user_log.timestamp
        elif "logged out" in user_log.action:
            active_sessions.pop(user_log.user_id, None)

    # Compute API averages per endpoint
    endpoint_durations: dict[str, list[int]] = {}
    for api_log in extracted.api_logs:
        endpoint_durations.setdefault(api_log.endpoint, []).append(
            api_log.duration_ms
        )

    api_averages: dict[str, float] = {}
    for endpoint, times in endpoint_durations.items():
        if times:
            api_averages[endpoint] = sum(times) / len(times)
        else:
            api_averages[endpoint] = 0.0

    return TransformedMetrics(
        error_counts=error_counts,
        api_averages=api_averages,
        active_sessions=active_sessions,
    )


def load_to_database(
    db_path: str,
    metrics: TransformedMetrics,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Loads aggregated metrics into the SQLite3 database securely using parameterized queries."""
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

        now = str(datetime.datetime.now())

        # Parameterized insertion of error counts
        for msg, count in metrics.error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        # Parameterized insertion of API averages
        for ep, avg in metrics.api_averages.items():
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(report_path: str, metrics: TransformedMetrics) -> None:
    """Generates an HTML report summarizing the parsed metrics."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in metrics.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    for ep, avg in metrics.api_averages.items():
        rounded_avg = round(avg, 1)
        lines.append(f"<tr><td>{ep}</td><td>{rounded_avg}</td></tr>")
    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{len(metrics.active_sessions)} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_pipeline() -> None:
    """Coordinates the Extract, Transform, and Load (ETL) pipeline."""
    log_file = os.getenv("LOG_FILE", "server.log")
    db_path = os.getenv("DB_PATH", "metrics.db")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port_str = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "admin")

    db_pass = os.getenv("DB_PASS", "password123")

    try:
        db_port = int(db_port_str)
    except ValueError:
        db_port = 5432

    # Extract
    extracted_data = extract(log_file)

    # Transform
    metrics = transform(extracted_data)

    # Load
    load_to_database(
        db_path=db_path,
        metrics=metrics,
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
    )
    generate_report("report.html", metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_file_default = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_file_default):
        with open(log_file_default, "w", encoding="utf-8") as fixture_file:
            fixture_file.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fixture_file.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fixture_file.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fixture_file.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fixture_file.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fixture_file.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
