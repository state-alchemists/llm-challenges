"""Refactored ETL pipeline for server log processing.

Reads server logs, aggregates metrics, persists them to SQLite,
and generates an HTML report. Configuration is externalised via
environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def get_config() -> Dict[str, str]:
    """Load runtime configuration from environment variables.

    Supported variables:
        DB_PATH      – SQLite database file path (default: metrics.db)
        LOG_FILE     – Path to the server log file (default: server.log)
        DB_HOST      – Database host name (default: localhost)
        DB_PORT      – Database port (default: 5432)
        DB_USER      – Database user name (default: admin)
        DB_PASS      – Database password (default: password123)
    """
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BaseEvent:
    """Shared fields for every parsed log event."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """Represents a user login/logout action."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEvent:
    """Represents an API call with measured latency."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedData:
    """Container for all extracted log data."""
    errors: List[BaseEvent] = field(default_factory=list)
    warnings: List[BaseEvent] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_events: List[ApiEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Base line:  "2024-01-01 12:00:00 INFO ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)

# User action:  "User 42 logged in"
_USER_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")

# API call:  "API /users/profile took 250ms"
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_log_lines(log_path: str) -> List[str]:
    """Read the log file and return a list of stripped, non-empty lines."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Transform (parse)
# ---------------------------------------------------------------------------

def parse_log_lines(lines: List[str]) -> ParsedData:
    """Parse raw log lines into structured events using regex.

    Rules:
      * ERROR   -> error event (message only)
      * WARN    -> warning event (message only)
      * INFO + "User ..." -> user event
      * INFO + "API ..."  -> API event
    """
    data = ParsedData()

    for line in lines:
        base_match = _LOG_LINE_RE.match(line)
        if not base_match:
            continue

        timestamp = f"{base_match.group('date')} {base_match.group('time')}"
        level = base_match.group("level")
        message = base_match.group("message")

        if level == "ERROR":
            data.errors.append(BaseEvent(timestamp=timestamp, level=level, message=message))

        elif level == "WARN":
            data.warnings.append(BaseEvent(timestamp=timestamp, level=level, message=message))

        elif level == "INFO":
            user_match = _USER_RE.match(message)
            if user_match:
                data.user_events.append(
                    UserEvent(
                        timestamp=timestamp,
                        user_id=user_match.group("uid"),
                        action=user_match.group("action"),
                    )
                )
                continue

            api_match = _API_RE.match(message)
            if api_match:
                data.api_events.append(
                    ApiEvent(
                        timestamp=timestamp,
                        endpoint=api_match.group("endpoint"),
                        duration_ms=int(api_match.group("duration")),
                    )
                )

    return data


def transform_error_summary(errors: List[BaseEvent]) -> Dict[str, int]:
    """Return a mapping of error message -> occurrence count."""
    summary: Dict[str, int] = {}
    for err in errors:
        summary[err.message] = summary.get(err.message, 0) + 1
    return summary


def transform_api_latency(api_events: List[ApiEvent]) -> Dict[str, float]:
    """Return average latency (ms) per API endpoint."""
    endpoint_times: Dict[str, List[int]] = {}
    for event in api_events:
        endpoint_times.setdefault(event.endpoint, []).append(event.duration_ms)
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }


def transform_active_sessions(user_events: List[UserEvent]) -> Dict[str, str]:
    """Determine currently active sessions from login/logout events.

    A session is considered active when a user has logged in but not yet
    logged out (the latest event for that user wins).
    """
    sessions: Dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return sessions


# ---------------------------------------------------------------------------
# Load (database + report)
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency: Dict[str, float],
) -> None:
    """Persist the transformed metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Mapping of error message -> count.
        api_latency: Mapping of endpoint -> average latency in ms.
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

        now = str(datetime.datetime.now())
        for msg, count in error_summary.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, avg_ms in api_latency.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_summary: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions: Dict[str, str],
) -> None:
    """Write an HTML report containing error summary, API latency, and active sessions.

    Args:
        report_path: Destination file path for the HTML report.
        error_summary: Mapping of error message -> count.
        api_latency: Mapping of endpoint -> average latency in ms.
        active_sessions: Mapping of user_id -> login timestamp for active sessions.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])
    for ep, avg in api_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(config: Dict[str, str]) -> None:
    """Execute the full Extract -> Transform -> Load pipeline."""
    lines = extract_log_lines(config["log_file"])
    parsed = parse_log_lines(lines)

    error_summary = transform_error_summary(parsed.errors)
    api_latency = transform_api_latency(parsed.api_events)
    active_sessions = transform_active_sessions(parsed.user_events)

    print(
        f"Connecting to database at {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )
    load_to_database(config["db_path"], error_summary, api_latency)

    generate_report("report.html", error_summary, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


def ensure_dummy_log(log_path: str) -> None:
    """Create a sample log file if none exists (useful for first-run demos)."""
    if os.path.exists(log_path):
        return
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(log_path, "w", encoding="utf-8") as f:
        f.writelines(sample_lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = get_config()
    ensure_dummy_log(cfg["log_file"])
    run_pipeline(cfg)
