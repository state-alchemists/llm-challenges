"""Pipeline for extracting, transforming, and loading server log data.

Reads server logs, aggregates errors and API metrics, persists results to
SQLite, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (all values from environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """An error log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A user session log entry (login or logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An API call log entry with latency measurement."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarningEvent:
    """A warning log entry."""

    timestamp: str
    message: str


# ---------------------------------------------------------------------------
# Compiled regex patterns for log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<payload>.+)$"
)

_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(
    log_path: str,
) -> tuple[list[ErrorEvent], list[UserEvent], list[ApiCall], list[WarningEvent]]:
    """Parse the server log file and categorize entries by type.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple of (errors, user_events, api_calls, warnings).
    """
    errors: list[ErrorEvent] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []
    warnings: list[WarningEvent] = []

    path = Path(log_path)
    if not path.exists():
        return errors, user_events, api_calls, warnings

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line.rstrip("\n"))
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            payload = match.group("payload")

            if level == "ERROR":
                errors.append(ErrorEvent(timestamp=timestamp, message=payload))
            elif level == "WARN":
                warnings.append(WarningEvent(timestamp=timestamp, message=payload))
            elif level == "INFO":
                user_match = _USER_RE.match(payload)
                if user_match:
                    user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action").strip(),
                        )
                    )
                    continue

                api_match = _API_RE.match(payload)
                if api_match:
                    api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration") or 0),
                        )
                    )

    return errors, user_events, api_calls, warnings


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_errors(errors: list[ErrorEvent]) -> dict[str, int]:
    """Aggregate error events into message-to-count mapping.

    Args:
        errors: Parsed error events from the extract phase.

    Returns:
        Mapping of error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def transform_api_metrics(api_calls: list[ApiCall]) -> dict[str, list[int]]:
    """Group API call durations by endpoint.

    Args:
        api_calls: Parsed API call events from the extract phase.

    Returns:
        Mapping of endpoint to a list of response times in milliseconds.
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def transform_active_sessions(user_events: list[UserEvent]) -> int:
    """Compute the number of currently active sessions.

    A login adds a session; a logout removes it.  Users still logged in
    at the end of the log are considered active.

    Args:
        user_events: Parsed user events from the extract phase.

    Returns:
        Number of active sessions.
    """
    active: set[str] = set()
    for event in user_events:
        if "logged in" in event.action:
            active.add(event.user_id)
        elif "logged out" in event.action:
            active.discard(event.user_id)
    return len(active)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    db_path: str,
) -> None:
    """Persist aggregated data to SQLite using parameterized queries.

    Args:
        error_counts: Error message to occurrence count mapping.
        api_metrics: Endpoint to response-time list mapping.
        db_path: Path to the SQLite database file.
    """
    now = str(datetime.datetime.now())
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for endpoint, times in api_metrics.items():
            avg_ms = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Generate an HTML report from aggregated data.

    Args:
        error_counts: Error message to occurrence count mapping.
        api_metrics: Endpoint to response-time list mapping.
        active_sessions: Number of active user sessions.
        output_path: File path for the generated HTML report.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_metrics.items():
        avg_ms = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the ETL pipeline: extract, transform, load."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    errors, user_events, api_calls, warnings = extract_log_entries(LOG_FILE)
    error_counts = transform_errors(errors)
    api_metrics = transform_api_metrics(api_calls)
    active_sessions = transform_active_sessions(user_events)

    load_to_database(error_counts, api_metrics, DB_PATH)
    generate_report(error_counts, api_metrics, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()