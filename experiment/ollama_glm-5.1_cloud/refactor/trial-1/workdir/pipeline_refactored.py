"""Server-log processing pipeline: Extract → Transform → Load.

Reads a server log file, aggregates error counts, API latency, and active
sessions, persists results to SQLite, and writes an HTML report.

All configuration (paths, credentials) comes from environment variables
with sensible defaults.  SQL uses parameterized queries exclusively.
Log parsing relies on compiled regex patterns.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration — environment variables with defaults
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("PIPELINE_LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("PIPELINE_REPORT_PATH", "report.html")

# Informational only — SQLite is file-based and does not use host/port/user.
DB_HOST: str = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.getenv("PIPELINE_DB_USER", "admin")
# DB_PASS is read from the environment but never logged or written anywhere.
os.getenv("PIPELINE_DB_PASS", "")  # noqa: S105 – deliberately unused

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """An ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A User login/logout INFO line."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API latency INFO line."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarningEntry:
    """A WARN-level log line."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all entries extracted from a log file."""

    errors: List[ErrorEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[WarningEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# "2024-01-01 12:00:00 LEVEL rest of message"
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<rest>.*)$",
)

# "User 42 logged in" | "User 42 logged out"
USER_EVENT_RE = re.compile(
    r"^User\s+(?P<user_id>\S+)\s+(?P<action>.*)$",
)

# "API /users/profile took 250ms" | "API /users/profile"
API_CALL_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$",
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: str) -> ParsedLog:
    """Parse the server log file into structured entries.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ParsedLog containing categorised log entries.
    """
    parsed = ParsedLog()
    path = Path(log_path)

    if not path.exists():
        return parsed

    with path.open("r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                parsed.errors.append(ErrorEntry(timestamp=timestamp, message=rest))

            elif level == "WARN":
                parsed.warnings.append(WarningEntry(timestamp=timestamp, message=rest))

            elif level == "INFO":
                user_match = USER_EVENT_RE.match(rest)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = API_CALL_RE.match(rest)
                if api_match:
                    duration = int(api_match.group("duration") or 0)
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=duration,
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_error_counts(errors: List[ErrorEntry]) -> Dict[str, int]:
    """Aggregate error messages into occurrence counts.

    Args:
        errors: List of ErrorEntry objects.

    Returns:
        Mapping of error message → occurrence count.
    """
    counts: Dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def transform_api_latency(api_calls: List[ApiCall]) -> Dict[str, List[int]]:
    """Group API call durations by endpoint.

    Args:
        api_calls: List of ApiCall objects.

    Returns:
        Mapping of endpoint → list of response times in ms.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def transform_active_sessions(user_events: List[UserEvent]) -> Dict[str, str]:
    """Compute currently active sessions from user login/logout events.

    A user is active when a "logged in" event has no matching "logged out".

    Args:
        user_events: List of UserEvent objects in chronological order.

    Returns:
        Mapping of user_id → login timestamp for active sessions.
    """
    sessions: Dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            del sessions[event.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
    db_path: str,
    db_host: str = DB_HOST,
    db_port: int = DB_PORT,
    db_user: str = DB_USER,
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    The host / port / user parameters are informational only — SQLite is
    file-based and does not authenticate over the network.

    Args:
        error_counts: Mapping of error message → occurrence count.
        api_latency: Mapping of endpoint → list of response times in ms.
        db_path: Path to the SQLite database file.
        db_host: Database host (informational).
        db_port: Database port (informational).
        db_user: Database user (informational).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat()

        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in api_latency.items():
            avg_ms = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    report_path: str = REPORT_PATH,
) -> None:
    """Write an HTML report summarising errors, API latency, and active sessions.

    Args:
        error_counts: Mapping of error message → occurrence count.
        api_latency: Mapping of endpoint → list of response times in ms.
        active_sessions: Mapping of user_id → login timestamp.
        report_path: Path to write the HTML report to.
    """
    lines: List[str] = [
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

    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    # Extract
    parsed = extract_log_entries(LOG_FILE)

    # Transform
    error_counts = transform_error_counts(parsed.errors)
    api_latency = transform_api_latency(parsed.api_calls)
    active_sessions = transform_active_sessions(parsed.user_events)

    # Load
    load_to_db(error_counts, api_latency, DB_PATH, DB_HOST, DB_PORT, DB_USER)
    generate_report(error_counts, api_latency, active_sessions, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


def create_sample_log(log_path: str) -> None:
    """Write a sample server log for testing when no log file exists."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(log_path, "w") as fh:
        fh.write("\n".join(sample_lines) + "\n")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        create_sample_log(LOG_FILE)
    run_pipeline()