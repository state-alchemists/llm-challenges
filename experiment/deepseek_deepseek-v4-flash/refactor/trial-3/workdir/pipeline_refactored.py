"""Server-log metrics pipeline (Extract -> Transform -> Load).

Reads an application server log, aggregates error / API-latency / active
session metrics, persists them to SQLite, and renders ``report.html`` with
the same sections as the original script (error summary, API latency table,
active session count).

All configuration is read from environment variables:

- ``LOG_FILE`` — path to the log file to parse (default ``server.log``)
- ``DB_PATH`` — path to the SQLite database (default ``metrics.db``)
- ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASS`` — connection
  metadata reported on startup (defaults ``localhost`` / ``5432`` / ``admin``)

When ``LOG_FILE`` does not exist the script writes a small sample log first,
preserving the original script's bootstrap behavior.

Security notes:
- SQL is always parameterized; log-derived values never reach a query string.
- Log-derived text is HTML-escaped before being embedded in the report.
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

# --------------------------------------------------------------------------
# Log grammar
# --------------------------------------------------------------------------

# 2024-01-01 12:00:00 ERROR Database timeout
_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) (?P<message>.*)$"
)
# User 42 logged in
_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.*)$")
# API /users/profile took 250ms
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?.*$")

# --------------------------------------------------------------------------
# Data records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorEvent:
    """A single ERROR log line."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class UserEvent:
    """An INFO log line describing a user action (login / logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiCall:
    """An INFO log line reporting an API request duration."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True)
class WarningEvent:
    """A single WARN log line."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class ExtractedLogs:
    """All typed events parsed from the log file, in file order."""

    errors: list[ErrorEvent]
    user_events: list[UserEvent]
    api_calls: list[ApiCall]
    warnings: list[WarningEvent]


@dataclass(frozen=True)
class ReportData:
    """Aggregated metrics that back the HTML report."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_session_count: int


@dataclass(frozen=True)
class Config:
    """Runtime configuration, all sourced from environment variables."""

    log_file: str
    db_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read configuration from environment variables, with sensible defaults."""
    return Config(
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_path=os.getenv("DB_PATH", "metrics.db"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# --------------------------------------------------------------------------
# Extract
# --------------------------------------------------------------------------


def parse_log_line(line: str) -> ErrorEvent | UserEvent | ApiCall | WarningEvent | None:
    """Parse one log line into a typed event, or ``None`` if it is not parseable.

    Replaces the original script's fragile whitespace splitting with regular
    expressions; lines that do not match the expected grammar are skipped.
    """
    match = _LINE_RE.match(line)
    if match is None:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message").strip()

    if level == "ERROR":
        return ErrorEvent(timestamp=timestamp, message=message)

    if level == "INFO":
        user_match = _USER_RE.match(message)
        if user_match is not None:
            return UserEvent(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action").strip(),
            )
        api_match = _API_RE.match(message)
        if api_match is not None:
            duration = api_match.group("duration_ms")
            return ApiCall(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(duration) if duration is not None else 0,
            )
        return None

    if level == "WARN":
        return WarningEvent(timestamp=timestamp, message=message)

    return None


def extract_events(log_file: str) -> ExtractedLogs:
    """Read the log file and parse every line into typed events.

    A missing log file yields an empty extraction (the original script's
    behavior); the caller decides whether to bootstrap a sample log first.
    """
    errors: list[ErrorEvent] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []
    warnings: list[WarningEvent] = []

    if not os.path.exists(log_file):
        return ExtractedLogs(errors, user_events, api_calls, warnings)

    with open(log_file, "r", encoding="utf-8") as handle:
        for line in handle:
            event = parse_log_line(line)
            if isinstance(event, ErrorEvent):
                errors.append(event)
            elif isinstance(event, UserEvent):
                user_events.append(event)
            elif isinstance(event, ApiCall):
                api_calls.append(event)
            elif isinstance(event, WarningEvent):
                warnings.append(event)

    return ExtractedLogs(errors, user_events, api_calls, warnings)


# --------------------------------------------------------------------------
# Transform
# --------------------------------------------------------------------------


def _track_active_sessions(user_events: list[UserEvent]) -> dict[str, str]:
    """Replay login/logout events in order and return currently active users."""
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return sessions


def transform_events(extracted: ExtractedLogs) -> ReportData:
    """Aggregate parsed events into report-ready metrics.

    Errors are counted by message, API calls are averaged per endpoint, and
    active sessions are tracked by replaying login/logout events in order.
    Warnings are extracted but, as in the original script, not aggregated.
    """
    error_counts: dict[str, int] = {}
    for event in extracted.errors:
        error_counts[event.message] = error_counts.get(event.message, 0) + 1

    latencies: dict[str, list[int]] = {}
    for call in extracted.api_calls:
        latencies.setdefault(call.endpoint, []).append(call.duration_ms)
    endpoint_avg_ms = {
        endpoint: sum(times) / len(times) for endpoint, times in latencies.items()
    }

    active_sessions = _track_active_sessions(extracted.user_events)
    return ReportData(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_session_count=len(active_sessions),
    )


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------


def load_metrics(report_data: ReportData, db_path: str) -> None:
    """Persist aggregated metrics into the SQLite database.

    All queries are parameterized (``?`` placeholders) — log-derived values
    never reach a query string, closing the original injection risk. A single
    run timestamp is used for every row written in one run.
    """
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        run_timestamp = str(datetime.now())
        for message, count in report_data.error_counts.items():
            connection.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (run_timestamp, message, count),
            )
        for endpoint, avg_ms in report_data.endpoint_avg_ms.items():
            connection.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (run_timestamp, endpoint, avg_ms),
            )


def generate_report(report_data: ReportData) -> str:
    """Render the HTML report (error summary, API latency, active sessions).

    Log-derived text is HTML-escaped to prevent markup injection; the section
    layout matches the original script.
    """
    rows: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in report_data.error_counts.items():
        rows.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    rows.append("</ul>")

    rows.append("<h2>API Latency</h2>")
    rows.append("<table border='1'>")
    rows.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg_ms in report_data.endpoint_avg_ms.items():
        rows.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    rows.append("</table>")

    rows.append("<h2>Active Sessions</h2>")
    rows.append(f"<p>{report_data.active_session_count} user(s) currently active</p>")
    rows.append("</body>")
    rows.append("</html>")
    return "\n".join(rows)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


def _ensure_sample_log(log_file: str) -> None:
    """Write a small sample log when ``log_file`` does not exist."""
    if os.path.exists(log_file):
        return
    with open(log_file, "w", encoding="utf-8") as handle:
        handle.write(_SAMPLE_LOG)


def main() -> None:
    """Run the full ETL pipeline and write ``report.html``."""
    config = load_config()
    _ensure_sample_log(config.log_file)

    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )

    extracted = extract_events(config.log_file)
    report_data = transform_events(extracted)
    load_metrics(report_data, config.db_path)

    with open("report.html", "w", encoding="utf-8") as handle:
        handle.write(generate_report(report_data))

    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    main()
