"""Pipeline for processing server logs into an HTML report.

Extracts log entries, transforms them into aggregated metrics,
loads them into a SQLite database, and generates a summary report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration – all values read from environment variables.
# Defaults match the original hard-coded values for standalone use.
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")
REPORT_PATH: str = os.getenv("REPORT_PATH", "report.html")

# ---------------------------------------------------------------------------
# Compiled regex patterns for log-line parsing
# ---------------------------------------------------------------------------
_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(INFO|ERROR|WARN)\s+(.+)$"
)
_USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.+)$")
_API_PATTERN = re.compile(r"^API\s+(\S+)\s+took\s+(\d+)ms$")


# ---------------------------------------------------------------------------
# Data classes for structured log entries
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A user session event (login / logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An API call with measured latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarningRecord:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all categorised log entries."""

    errors: list[ErrorRecord] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def extract_log_entries(log_path: str) -> ParsedLog:
    """Parse a server log file into structured records.

    Uses compiled regex patterns to robustly identify log levels,
    user events, and API calls regardless of spacing variations.

    Args:
        log_path: Filesystem path to the log file.

    Returns:
        A ParsedLog containing categorised entry lists.
    """
    parsed = ParsedLog()
    path = Path(log_path)
    if not path.exists():
        return parsed

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp, level, payload = match.group(1), match.group(2), match.group(3)

            if level == "ERROR":
                parsed.errors.append(
                    ErrorRecord(timestamp=timestamp, message=payload)
                )
            elif level == "WARN":
                parsed.warnings.append(
                    WarningRecord(timestamp=timestamp, message=payload)
                )
            elif level == "INFO":
                user_match = _USER_PATTERN.match(payload)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group(1),
                            action=user_match.group(2),
                        )
                    )
                    continue

                api_match = _API_PATTERN.match(payload)
                if api_match:
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group(1),
                            duration_ms=int(api_match.group(2)),
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def transform_error_counts(errors: list[ErrorRecord]) -> dict[str, int]:
    """Aggregate error records into message-to-frequency mapping.

    Args:
        errors: List of ErrorRecord instances.

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
        api_calls: List of ApiCall instances.

    Returns:
        Mapping of endpoint name to list of latency values in milliseconds.
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def transform_active_sessions(user_events: list[UserEvent]) -> int:
    """Count users whose login has not been matched by a logout.

    Args:
        user_events: List of UserEvent instances.

    Returns:
        Number of currently active sessions.
    """
    sessions: set[str] = set()
    for event in user_events:
        if event.action == "logged in":
            sessions.add(event.user_id)
        elif event.action == "logged out":
            sessions.discard(event.user_id)
    return len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
) -> None:
    """Persist aggregated metrics into a SQLite database.

    Uses parameterised queries (? placeholders) to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message to count.
        api_metrics: Mapping of endpoint to list of latency values.
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
        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in api_metrics.items():
            avg_ms = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    active_sessions: int,
    report_path: str,
) -> None:
    """Render an HTML summary report from aggregated metrics.

    Args:
        error_counts: Mapping of error message to occurrence count.
        api_metrics: Mapping of endpoint name to list of latency values.
        active_sessions: Count of currently active user sessions.
        report_path: Filesystem path for the output HTML file.
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
        avg_ms = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg_ms}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(report_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    """Execute the full Extract-Transform-Load pipeline.

    Reads configuration from environment variables, parses the log file,
    aggregates metrics, persists to the database, and writes the report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed = extract_log_entries(LOG_FILE)
    error_counts = transform_error_counts(parsed.errors)
    api_metrics = transform_api_metrics(parsed.api_calls)
    active_sessions = transform_active_sessions(parsed.user_events)

    load_to_database(DB_PATH, error_counts, api_metrics)
    generate_report(error_counts, api_metrics, active_sessions, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    run_pipeline()