"""Server-log processing pipeline.

Extracts structured records from a server log file, transforms them into
aggregated metrics, loads the results into a SQLite database, and generates
an HTML report.

Configuration is read from environment variables with sensible defaults:
  LOG_FILE      – path to the server log                (default: server.log)
  DB_PATH       – path to the SQLite database           (default: metrics.db)
  DB_HOST       – database host (used in log output)    (default: localhost)
  DB_PORT       – database port (used in log output)    (default: 5432)
  DB_USER       – database user (used in log output)    (default: admin)
  DB_PASS       – database password (used in log output)(default: password123)
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user login / logout INFO entry."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API latency INFO entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarningEvent:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all records extracted from a log file."""

    errors: List[ErrorEvent] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[WarningEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# General log line: "2024-01-01 12:00:00 LEVEL ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<rest>.*)$"
)

# User action line: "User <id> <action>"
_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# API call line: "API <endpoint> took <n>ms"
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$")

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_lines(path: str) -> List[str]:
    """Read the log file and return its lines.

    Args:
        path: Filesystem path to the server log.

    Returns:
        A list of stripped, non-empty lines from the log file.
        Returns an empty list if the file does not exist.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        return [line.strip() for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def parse_log(lines: List[str]) -> ParsedLog:
    """Parse raw log lines into structured records.

    Each line is matched against regex patterns to determine its type
    (ERROR, INFO with a User/API marker, or WARN) and extracted into
    the corresponding dataclass.

    Args:
        lines: Non-empty, stripped log lines.

    Returns:
        A ``ParsedLog`` with all recognised records.
    """
    parsed = ParsedLog()

    for line in lines:
        match = _LOG_LINE_RE.match(line)
        if not match:
            continue

        timestamp = match.group("timestamp")
        level = match.group("level")
        rest = match.group("rest")

        if level == "ERROR":
            parsed.errors.append(ErrorEvent(timestamp=timestamp, message=rest))

        elif level == "INFO":
            user_match = _USER_RE.match(rest)
            if user_match:
                parsed.user_events.append(
                    UserEvent(
                        timestamp=timestamp,
                        user_id=user_match.group("user_id"),
                        action=user_match.group("action"),
                    )
                )
                continue

            api_match = _API_RE.match(rest)
            if api_match:
                parsed.api_calls.append(
                    ApiCall(
                        timestamp=timestamp,
                        endpoint=api_match.group("endpoint"),
                        duration_ms=int(api_match.group("ms")),
                    )
                )

        elif level == "WARN":
            parsed.warnings.append(WarningEvent(timestamp=timestamp, message=rest))

    return parsed


def compute_error_counts(errors: List[ErrorEvent]) -> Dict[str, int]:
    """Aggregate error occurrences by message.

    Args:
        errors: The list of ``ErrorEvent`` records.

    Returns:
        A mapping of error message → occurrence count.
    """
    counts: Dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def compute_api_latency(
    api_calls: List[ApiCall],
) -> Dict[str, List[int]]:
    """Group API call durations by endpoint.

    Args:
        api_calls: The list of ``ApiCall`` records.

    Returns:
        A mapping of endpoint → list of durations in ms.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def compute_active_sessions(user_events: List[UserEvent]) -> int:
    """Count sessions that logged in but never logged out.

    Args:
        user_events: The list of ``UserEvent`` records (must be in
            chronological order).

    Returns:
        The number of users currently active.
    """
    logged_in: set[str] = set()
    for event in user_events:
        if "logged in" in event.action:
            logged_in.add(event.user_id)
        elif "logged out" in event.action:
            logged_in.discard(event.user_id)
    return len(logged_in)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(
    db_path: str,
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics into the SQLite database.

    Uses parameterised queries throughout to prevent SQL injection.

    Args:
        db_path:  Path to the SQLite database file.
        error_counts: Mapping of error message → count.
        api_latency:  Mapping of endpoint → list of durations.
    """
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Write an HTML report to *output_path*.

    The report contains three sections matching the original output:
      - Error Summary (message + count)
      - API Latency table (endpoint + average ms)
      - Active Session count

    All dynamic values are HTML-escaped to prevent injection.

    Args:
        error_counts:   Mapping of error message → count.
        api_latency:    Mapping of endpoint → list of durations.
        active_sessions: Number of currently active users.
        output_path:    Path to write the HTML report to.
    """
    parts: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        parts.append(
            f"<li><b>{html.escape(msg)}</b>: {html.escape(str(count))} occurrences</li>"
        )

    parts.append("</ul>")
    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        parts.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{html.escape(str(avg))}</td></tr>"
        )

    parts.append("</table>")
    parts.append("<h2>Active Sessions</h2>")
    parts.append(
        f"<p>{html.escape(str(active_sessions))} user(s) currently active</p>"
    )
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w") as fh:
        fh.write("\n".join(parts) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def create_sample_log(path: str) -> None:
    """Write a sample log file for development / testing.

    Args:
        path: Filesystem path to write the sample log to.
    """
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(path, "w") as fh:
        fh.write("\n".join(sample_lines) + "\n")


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline.

    1. Reads the log file (creates a sample if it does not exist).
    2. Parses lines into structured records.
    3. Aggregates errors, API latency, and active sessions.
    4. Persists results to SQLite.
    5. Generates ``report.html``.
    """
    if not os.path.exists(LOG_FILE):
        create_sample_log(LOG_FILE)

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    lines = extract_log_lines(LOG_FILE)

    # Transform
    parsed = parse_log(lines)
    error_counts = compute_error_counts(parsed.errors)
    api_latency = compute_api_latency(parsed.api_calls)
    active_sessions = compute_active_sessions(parsed.user_events)

    # Load
    load_to_db(DB_PATH, error_counts, api_latency)
    generate_report(error_counts, api_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()