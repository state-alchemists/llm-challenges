"""Refactored log-processing pipeline.

Reads a server log, extracts structured events, transforms them into report
statistics (error counts, API latency averages, active session count), and
loads them into SQLite plus an HTML report.

All configuration comes from environment variables; no credentials or paths
are hardcoded. SQL is written with parameterized queries, and log lines are
parsed with regular expressions instead of fragile string splitting.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass

# --- Configuration (all overridable via environment variables) ------------

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
REPORT_FILE = os.environ.get("REPORT_FILE", "report.html")

# Kept for parity with the original config surface. Storage is SQLite, so
# these are not used by sqlite3; they are read from the environment so a
# future migration to a server-backed DB starts from env vars, not literals.
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "")

# --- Log parsing ------------------------------------------------------------

_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) (?P<message>.+)$"
)
_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@dataclass(frozen=True)
class ErrorEvent:
    """A log line at ERROR level."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class UserEvent:
    """A log line reporting a user action (login or logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiCall:
    """A log line reporting an API request and its duration."""

    timestamp: str
    endpoint: str
    duration_ms: int


ParsedEvent = ErrorEvent | UserEvent | ApiCall | None


@dataclass(frozen=True)
class ParsedLogs:
    """Structured events extracted from the raw log."""

    errors: list[ErrorEvent]
    users: list[UserEvent]
    api_calls: list[ApiCall]


@dataclass(frozen=True)
class TransformResult:
    """Report-ready statistics derived from parsed events."""

    error_counts: dict[str, int]
    api_latency: dict[str, float]
    active_sessions: set[str]


# --- Extract ----------------------------------------------------------------

def ensure_log_file(log_path: str) -> None:
    """Create a small sample log when none exists so the script runs standalone."""
    if os.path.exists(log_path):
        return
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(_SAMPLE_LOG)


def extract_log_entries(log_path: str) -> ParsedLogs:
    """Read the log file and parse every line into a structured event."""
    errors: list[ErrorEvent] = []
    users: list[UserEvent] = []
    api_calls: list[ApiCall] = []

    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            event = _parse_log_line(line)
            if isinstance(event, ErrorEvent):
                errors.append(event)
            elif isinstance(event, UserEvent):
                users.append(event)
            elif isinstance(event, ApiCall):
                api_calls.append(event)

    return ParsedLogs(errors=errors, users=users, api_calls=api_calls)


def _parse_log_line(line: str) -> ParsedEvent:
    """Parse one log line into an event, or None for irrelevant lines.

    WARN lines and INFO lines without a User/API payload carry no data the
    report uses, so they are dropped here.
    """
    match = _LINE_RE.match(line)
    if match is None:
        return None

    timestamp = f"{match.group('date')} {match.group('time')}"
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return ErrorEvent(timestamp=timestamp, message=message.strip())
    if level != "INFO":
        return None

    user_match = _USER_RE.match(message)
    if user_match is not None:
        return UserEvent(
            timestamp=timestamp,
            user_id=user_match.group("user_id"),
            action=user_match.group("action"),
        )

    api_match = _API_RE.match(message)
    if api_match is not None:
        duration = api_match.group("duration")
        return ApiCall(
            timestamp=timestamp,
            endpoint=api_match.group("endpoint"),
            duration_ms=int(duration) if duration is not None else 0,
        )

    return None


# --- Transform ---------------------------------------------------------------

def transform_logs(parsed: ParsedLogs) -> TransformResult:
    """Aggregate parsed events into the statistics the report displays."""
    return TransformResult(
        error_counts=_count_errors(parsed.errors),
        api_latency=_average_latencies(parsed.api_calls),
        active_sessions=_track_sessions(parsed.users),
    )


def _count_errors(errors: list[ErrorEvent]) -> dict[str, int]:
    """Return {message: occurrence count} preserving first-seen order."""
    counts: dict[str, int] = {}
    for event in errors:
        counts[event.message] = counts.get(event.message, 0) + 1
    return counts


def _average_latencies(api_calls: list[ApiCall]) -> dict[str, float]:
    """Return {endpoint: average duration in ms} preserving first-seen order."""
    durations: dict[str, list[int]] = {}
    for call in api_calls:
        durations.setdefault(call.endpoint, []).append(call.duration_ms)
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in durations.items()
    }


def _track_sessions(users: list[UserEvent]) -> set[str]:
    """Return the set of user ids still logged in after all events."""
    active: set[str] = set()
    for event in users:
        if "logged in" in event.action:
            active.add(event.user_id)
        elif "logged out" in event.action:
            active.discard(event.user_id)
    return active


# --- Load -------------------------------------------------------------------

def init_database(db_path: str) -> sqlite3.Connection:
    """Open the SQLite database and ensure the report tables exist."""
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return connection


def load_metrics(connection: sqlite3.Connection, result: TransformResult) -> None:
    """Persist error counts and API latency averages with parameterized queries."""
    timestamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    for message, count in result.error_counts.items():
        connection.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (timestamp, message, count),
        )
    for endpoint, avg in result.api_latency.items():
        connection.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (timestamp, endpoint, avg),
        )
    connection.commit()


def write_report(report_path: str, result: TransformResult) -> None:
    """Write report.html with the error summary, latency table, and session count."""
    parts = [
        "<html>\n<head><title>System Report</title></head>\n<body>\n",
        "<h1>Error Summary</h1>\n<ul>\n",
    ]
    for message, count in result.error_counts.items():
        parts.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>\n")
    parts.append("</ul>\n")
    parts.append("<h2>API Latency</h2>\n<table border='1'>\n")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n")
    for endpoint, avg in result.api_latency.items():
        parts.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg, 1)}</td></tr>\n"
        )
    parts.append("</table>\n")
    parts.append("<h2>Active Sessions</h2>\n")
    parts.append(f"<p>{len(result.active_sessions)} user(s) currently active</p>\n")
    parts.append("</body>\n</html>")

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write("".join(parts))


# --- Orchestration -----------------------------------------------------------

def main() -> None:
    """Run the extract-transform-load pipeline and produce the HTML report."""
    ensure_log_file(LOG_FILE)
    parsed = extract_log_entries(LOG_FILE)
    result = transform_logs(parsed)

    print(f"Connecting to SQLite database at {DB_PATH}...")
    connection = init_database(DB_PATH)
    try:
        load_metrics(connection, result)
    finally:
        connection.close()

    write_report(REPORT_FILE, result)
    print(
        "Job finished at "
        + datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    )


if __name__ == "__main__":
    main()
