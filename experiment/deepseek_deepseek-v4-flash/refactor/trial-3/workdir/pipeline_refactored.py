"""Extract -> Transform -> Load pipeline for server logs.

Reads raw lines from a server log file, parses each line with regular
expressions into structured records, aggregates error counts, per-endpoint
API latency, and the set of currently active user sessions, then loads the
aggregates into a SQLite database and renders ``report.html``.

Configuration (log file path, database path, credentials) is read from
environment variables -- ``LOG_FILE``, ``DB_PATH``, ``DB_HOST``, ``DB_PORT``,
``DB_USER``, ``DB_PASS``, ``REPORT_FILE`` -- so no paths or secrets are
hardcoded in the source.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    log_file: Path
    db_path: Path
    report_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_password: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from ``LOG_FILE``/``DB_*``/``REPORT_FILE`` env vars."""
        return cls(
            log_file=Path(os.environ.get("LOG_FILE", "server.log")),
            db_path=Path(os.environ.get("DB_PATH", "metrics.db")),
            report_file=Path(os.environ.get("REPORT_FILE", "report.html")),
            db_host=os.environ.get("DB_HOST", "localhost"),
            db_port=int(os.environ.get("DB_PORT", "5432")),
            db_user=os.environ.get("DB_USER", "admin"),
            db_password=os.environ.get("DB_PASS", ""),
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_SAMPLE_LOG_LINES = (
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
)


def ensure_log_file(log_file: Path) -> None:
    """Create a sample log file if ``log_file`` does not exist.

    Mirrors the original script's bootstrap behavior so the pipeline can be
    demonstrated on a fresh checkout.
    """
    if not log_file.exists():
        log_file.write_text("\n".join(_SAMPLE_LOG_LINES) + "\n", encoding="utf-8")


def extract(log_file: Path) -> list[str]:
    """Read raw log lines from ``log_file``.

    Args:
        log_file: Path to the log file.

    Returns:
        The file's lines with surrounding whitespace removed.
    """
    return [
        line.strip() for line in log_file.read_text(encoding="utf-8").splitlines()
    ]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) (?P<payload>.*)$"
)
_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$")


@dataclass(frozen=True)
class ErrorRecord:
    """A single ERROR line from the log."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class WarningRecord:
    """A single WARN line from the log."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class UserEvent:
    """A single INFO User login/logout line from the log."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiCall:
    """A single INFO API call line from the log."""

    timestamp: str
    endpoint: str
    duration_ms: int


LogEvent = ErrorRecord | WarningRecord | UserEvent | ApiCall


@dataclass(frozen=True)
class ParsedLog:
    """Structured records extracted from the raw log."""

    errors: list[ErrorRecord]
    warnings: list[WarningRecord]
    api_calls: list[ApiCall]
    active_sessions: dict[str, str]


def parse_line(line: str) -> LogEvent | None:
    """Parse a single log line into a structured event.

    Returns ``None`` for lines that do not match the expected format or use
    an unrecognized log level.
    """
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None
    timestamp = match.group("timestamp")
    level = match.group("level")
    payload = match.group("payload").strip()

    if level == "ERROR":
        return ErrorRecord(timestamp=timestamp, message=payload)
    if level == "WARN":
        return WarningRecord(timestamp=timestamp, message=payload)
    if level == "INFO":
        user_match = _USER_RE.match(payload)
        if user_match is not None:
            return UserEvent(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action").strip(),
            )
        api_match = _API_RE.match(payload)
        if api_match is not None:
            return ApiCall(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("duration_ms") or 0),
            )
    return None


def transform(lines: list[str]) -> ParsedLog:
    """Parse raw log lines into structured records and track sessions.

    Applies ``parse_line`` to every line and maintains the set of active user
    sessions by applying login/logout events in log order.
    """
    errors: list[ErrorRecord] = []
    warnings: list[WarningRecord] = []
    api_calls: list[ApiCall] = []
    active_sessions: dict[str, str] = {}

    for line in lines:
        event = parse_line(line)
        if isinstance(event, ErrorRecord):
            errors.append(event)
        elif isinstance(event, WarningRecord):
            warnings.append(event)
        elif isinstance(event, ApiCall):
            api_calls.append(event)
        elif isinstance(event, UserEvent):
            if "logged in" in event.action:
                active_sessions[event.user_id] = event.timestamp
            elif "logged out" in event.action and event.user_id in active_sessions:
                active_sessions.pop(event.user_id)

    return ParsedLog(
        errors=errors,
        warnings=warnings,
        api_calls=api_calls,
        active_sessions=active_sessions,
    )


@dataclass(frozen=True)
class Aggregates:
    """Data ready for persistence and reporting."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_session_count: int


def aggregate(parsed: ParsedLog) -> Aggregates:
    """Summarize parsed records into report-ready aggregates.

    - Error messages are counted by exact message text.
    - API durations are averaged per endpoint.
    - The number of currently active sessions is counted.
    """
    error_counts: dict[str, int] = {}
    for record in parsed.errors:
        error_counts[record.message] = error_counts.get(record.message, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.duration_ms)

    endpoint_avg_ms = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }

    return Aggregates(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_session_count=len(parsed.active_sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

_CREATE_ERRORS_TABLE = (
    "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
)
_CREATE_API_METRICS_TABLE = (
    "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
)


def load(config: Config, aggregates: Aggregates) -> None:
    """Persist aggregates to SQLite and write the HTML report."""
    _write_metrics_db(config.db_path, aggregates)
    render_report(aggregates, config.report_file)


def _error_rows(
    aggregates: Aggregates,
) -> Iterator[tuple[str, str, int]]:
    """Yield ``(timestamp, message, count)`` rows for the errors table."""
    for message, count in aggregates.error_counts.items():
        yield datetime.datetime.now().isoformat(sep=" "), message, count


def _api_rows(
    aggregates: Aggregates,
) -> Iterator[tuple[str, str, float]]:
    """Yield ``(timestamp, endpoint, avg_ms)`` rows for the api_metrics table."""
    for endpoint, avg_ms in aggregates.endpoint_avg_ms.items():
        yield datetime.datetime.now().isoformat(sep=" "), endpoint, avg_ms


def _write_metrics_db(db_path: Path, aggregates: Aggregates) -> None:
    """Insert error counts and endpoint averages into the SQLite database.

    Uses parameterized queries only; no user data is interpolated into SQL.
    """
    with sqlite3.connect(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(_CREATE_ERRORS_TABLE)
        cursor.execute(_CREATE_API_METRICS_TABLE)
        cursor.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            _error_rows(aggregates),
        )
        cursor.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            _api_rows(aggregates),
        )


def render_report(aggregates: Aggregates, report_file: Path) -> None:
    """Write report.html with error summary, API latency, and session count.

    All dynamic values are HTML-escaped before interpolation.
    """
    parts: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    parts.extend(
        f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        for message, count in aggregates.error_counts.items()
    )
    parts.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    parts.extend(
        f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg_ms, 1)}</td></tr>"
        for endpoint, avg_ms in aggregates.endpoint_avg_ms.items()
    )
    parts.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{aggregates.active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    report_file.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full extract -> transform -> load pipeline."""
    config = Config.from_env()
    ensure_log_file(config.log_file)
    lines = extract(config.log_file)
    parsed = transform(lines)
    aggregates = aggregate(parsed)
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    load(config, aggregates)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
