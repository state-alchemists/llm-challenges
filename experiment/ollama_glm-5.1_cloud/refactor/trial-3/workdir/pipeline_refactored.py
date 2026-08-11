"""Server-log processing pipeline.

Extracts structured records from a server log, transforms them into
error summaries and API-latency statistics, and loads the results into
a SQLite database and an HTML report.

All configuration is read from environment variables with sensible
defaults so the script works out of the box in development.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration (environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("PIPELINE_LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("PIPELINE_REPORT_PATH", "report.html")
DB_HOST: str = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.getenv("PIPELINE_DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Log-line regex patterns
# ---------------------------------------------------------------------------

# 2024-01-01 12:00:00 INFO  ...
_LOG_LINE_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|WARN|ERROR)\s+"
    r"(?P<rest>.*)"
)

# INFO User 42 logged in
_USER_ACTION_RE = re.compile(
    r"User\s+(?P<user_id>\S+)\s+(?P<action>.*)"
)

# INFO API /users/profile took 250ms
_API_CALL_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ErrorRecord:
    """A single error occurrence parsed from the log."""

    timestamp: str
    message: str


@dataclass
class UserAction:
    """A user login/logout event parsed from the log."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with latency parsed from the log."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarningRecord:
    """A warning parsed from the log."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Aggregated result of parsing the entire log file."""

    errors: list[ErrorRecord] = field(default_factory=list)
    user_actions: list[UserAction] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningRecord] = field(default_factory=list)


@dataclass
class ErrorSummary:
    """Error message → occurrence count."""

    message: str
    count: int


@dataclass
class EndpointLatency:
    """Per-endpoint average latency."""

    endpoint: str
    avg_ms: float


# ---------------------------------------------------------------------------
# Extract – read and parse the log file
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Parse *log_path* into structured records.

    Uses regex to robustly identify timestamps, log levels, user
    actions, API calls, errors, and warnings.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ``ParsedLog`` containing all recognised records.
    """
    result = ParsedLog()

    if not os.path.exists(log_path):
        return result

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line.strip())
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                result.errors.append(
                    ErrorRecord(timestamp=timestamp, message=rest)
                )

            elif level == "WARN":
                result.warnings.append(
                    WarningRecord(timestamp=timestamp, message=rest)
                )

            elif level == "INFO":
                user_match = _USER_ACTION_RE.match(rest)
                if user_match:
                    result.user_actions.append(
                        UserAction(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_CALL_RE.match(rest)
                if api_match:
                    result.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            latency_ms=int(api_match.group("ms")),
                        )
                    )

    return result


# ---------------------------------------------------------------------------
# Transform – compute summaries
# ---------------------------------------------------------------------------


def _compute_error_summary(errors: list[ErrorRecord]) -> list[ErrorSummary]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return [ErrorSummary(message=msg, count=c) for msg, c in counts.items()]


def _compute_endpoint_latency(
    api_calls: list[ApiCall],
) -> list[EndpointLatency]:
    """Compute average latency per endpoint."""
    buckets: dict[str, list[int]] = {}
    for call in api_calls:
        buckets.setdefault(call.endpoint, []).append(call.latency_ms)
    return [
        EndpointLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in buckets.items()
    ]


def _compute_active_sessions(
    user_actions: list[UserAction],
) -> dict[str, str]:
    """Return ``{user_id: login_timestamp}`` for currently active users.

    A session is active when a "logged in" action has no matching
    "logged out" for the same user.
    """
    sessions: dict[str, str] = {}
    for action in user_actions:
        if action.action == "logged in":
            sessions[action.user_id] = action.timestamp
        elif action.action == "logged out" and action.user_id in sessions:
            sessions.pop(action.user_id)
    return sessions


def transform(parsed: ParsedLog) -> tuple[
    list[ErrorSummary],
    list[EndpointLatency],
    dict[str, str],
]:
    """Derive summaries from parsed log data.

    Args:
        parsed: The output of :func:`extract`.

    Returns:
        A triple of ``(error_summary, endpoint_latency, active_sessions)``.
    """
    error_summary = _compute_error_summary(parsed.errors)
    endpoint_latency = _compute_endpoint_latency(parsed.api_calls)
    active_sessions = _compute_active_sessions(parsed.user_actions)
    return error_summary, endpoint_latency, active_sessions


# ---------------------------------------------------------------------------
# Load – persist to database and generate HTML report
# ---------------------------------------------------------------------------


def load_db(
    error_summary: list[ErrorSummary],
    endpoint_latency: list[EndpointLatency],
    db_path: str,
) -> None:
    """Insert error and latency summaries into the SQLite database.

    Uses parameterised queries to prevent SQL injection.

    Args:
        error_summary: Per-message error counts.
        endpoint_latency: Per-endpoint average latencies.
        db_path: Path to the SQLite database file.
    """
    now = datetime.datetime.now()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for err in error_summary:
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now.isoformat(), err.message, err.count),
        )

    for ep in endpoint_latency:
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now.isoformat(), ep.endpoint, ep.avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: list[ErrorSummary],
    endpoint_latency: list[EndpointLatency],
    active_sessions: dict[str, str],
) -> str:
    """Render an HTML report from the computed summaries.

    Args:
        error_summary: Per-message error counts.
        endpoint_latency: Per-endpoint average latencies.
        active_sessions: Active user sessions.

    Returns:
        A complete HTML document as a string.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err in error_summary:
        lines.append(
            f"<li><b>{err.message}</b>: {err.count} occurrences</li>"
        )
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep in endpoint_latency:
        lines.append(
            f"<tr><td>{ep.endpoint}</td><td>{round(ep.avg_ms, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def load(
    error_summary: list[ErrorSummary],
    endpoint_latency: list[EndpointLatency],
    active_sessions: dict[str, str],
    db_path: str,
    report_path: str,
) -> None:
    """Persist summaries to the database and write the HTML report.

    Args:
        error_summary: Per-message error counts.
        endpoint_latency: Per-endpoint average latencies.
        active_sessions: Active user sessions.
        db_path: Path to the SQLite database.
        report_path: Path for the output HTML report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    load_db(error_summary, endpoint_latency, db_path)

    html = generate_report(error_summary, endpoint_latency, active_sessions)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_SAMPLE_LOG_LINES: str = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write(_SAMPLE_LOG_LINES)

    parsed = extract(LOG_FILE)
    error_summary, endpoint_latency, active_sessions = transform(parsed)
    load(error_summary, endpoint_latency, active_sessions, DB_PATH, REPORT_PATH)


if __name__ == "__main__":
    main()