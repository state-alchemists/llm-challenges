"""
Log processing pipeline: Extract → Transform → Load → Report.

Parses a structured server log, aggregates error counts and API latency
metrics into SQLite, and produces an HTML summary.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Configuration (all read from environment with safe defaults for development)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")  # no default — must be set


# ---------------------------------------------------------------------------
# Structured data types
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """A single error record extracted from a log line."""

    timestamp: str
    message: str


@dataclass
class ApiCallEntry:
    """A single API latency record extracted from a log line."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class UserActionEntry:
    """A single user-session action extracted from a log line."""

    timestamp: str
    user_id: str
    action: str  # e.g. "logged in", "logged out"


# Typed extraction result so callers know exactly what fields are present
@dataclass
class ParsedLogLine:
    """Union of all possible parsed record types from one log line."""

    errors: list[ErrorEntry] = field(default_factory=list)
    api_calls: list[ApiCallEntry] = field(default_factory=list)
    user_actions: list[UserActionEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level for efficiency)
# ---------------------------------------------------------------------------

# Log format: 2024-01-01 12:00:00 LEVEL Message...
_LOG_COMMON_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.*)$"
)

# ERROR line: message is everything after the level
_ERROR_PATTERN = re.compile(r"(?P<message>.+)$")

# INFO + User line: "User {uid} {action}"
_USER_ACTION_PATTERN = re.compile(
    r"^User (?P<uid>\S+) (?P<action>logged in|logged out).*$"
)

# INFO + API line: "API /endpoint took Nms"
_API_LATENCY_PATTERN = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT phase
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> ParsedLogLine:
    """
    Parse a single log line into its structured components.

    Returns a ``ParsedLogLine`` that may contain zero or more of:
    - one error
    - one API call record
    - one user-action record
    - one warning message
    """
    result = ParsedLogLine()

    m = _LOG_COMMON_PATTERN.match(line)
    if not m:
        return result

    timestamp = m.group("timestamp")
    level = m.group("level")
    rest = m.group("rest")

    if level == "ERROR":
        err_m = _ERROR_PATTERN.match(rest)
        if err_m:
            result.errors.append(ErrorEntry(timestamp=timestamp, message=err_m.group("message")))

    elif level == "INFO":
        user_m = _USER_ACTION_PATTERN.match(rest)
        if user_m:
            result.user_actions.append(
                UserActionEntry(
                    timestamp=timestamp,
                    user_id=user_m.group("uid"),
                    action=user_m.group("action"),
                )
            )
            return result  # no other INFO variants handled below

        api_m = _API_LATENCY_PATTERN.match(rest)
        if api_m:
            result.api_calls.append(
                ApiCallEntry(
                    timestamp=timestamp,
                    endpoint=api_m.group("endpoint"),
                    duration_ms=int(api_m.group("ms")),
                )
            )

    elif level == "WARN":
        result.warnings.append(rest)

    return result


def extract_logs(log_path: str) -> tuple[list[ErrorEntry], list[ApiCallEntry], list[UserActionEntry]]:
    """
    Read *log_path* and extract all structured records.

    Returns:
        A three-element tuple of (errors, api_calls, user_actions).
    """
    errors: list[ErrorEntry] = []
    api_calls: list[ApiCallEntry] = []
    user_actions: list[UserActionEntry] = []

    path = Path(log_path)
    if not path.is_file():
        return errors, api_calls, user_actions

    with path.open() as fh:
        for line in fh:
            parsed = parse_log_line(line)
            errors.extend(parsed.errors)
            api_calls.extend(parsed.api_calls)
            user_actions.extend(parsed.user_actions)

    return errors, api_calls, user_actions


# ---------------------------------------------------------------------------
# TRANSFORM phase
# ---------------------------------------------------------------------------


def compute_error_summary(errors: list[ErrorEntry]) -> dict[str, int]:
    """
    Aggregate error messages into counts.

    Returns:
        Mapping from error message text → occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def compute_api_stats(api_calls: list[ApiCallEntry]) -> dict[str, list[int]]:
    """
    Group API calls by endpoint and collect duration values.

    Returns:
        Mapping from endpoint → list of duration_ms values (for averaging).
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def compute_active_session_count(
    user_actions: list[UserActionEntry],
) -> int:
    """
    Track "logged in" / "logged out" events and return currently active count.

    Each distinct user_id increments on login and decrements on logout.
    Users with no matching logout are still counted as active.
    """
    active: set[str] = set()
    for action in user_actions:
        if action.action == "logged in":
            active.add(action.user_id)
        elif action.action == "logged out":
            active.discard(action.user_id)
    return len(active)


# ---------------------------------------------------------------------------
# LOAD phase
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """
    Write *error_summary* and *api_stats* into the SQLite database at *db_path*.

    Uses parameterized queries (``?`` placeholders) to prevent SQL injection.
    Creates tables if they do not exist.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now()

    for msg, count in error_summary.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now.isoformat(), msg, count),
        )

    for endpoint, durations in api_stats.items():
        avg = sum(durations) / len(durations)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now.isoformat(), endpoint, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# REPORT phase
# ---------------------------------------------------------------------------


def generate_html_report(
    output_path: str,
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """
    Render the final HTML report to *output_path*.

    Includes:
    - Error summary (message → count)
    - API latency table (endpoint → average ms)
    - Active session count
    """
    rows_errors = "".join(
        f"<li><b>{msg}</b>: {count} occurrences</li>"
        for msg, count in error_summary.items()
    )

    rows_api = "".join(
        f"<tr><td>{ep}</td><td>{round(sum(durations) / len(durations), 1)}</td></tr>"
        for ep, durations in api_stats.items()
    )

    html = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        f"<h1>Error Summary</h1>\n<ul>\n{rows_errors}</ul>\n"
        "<h2>API Latency</h2>\n"
        "<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        f"{rows_api}"
        "</table>\n"
        "<h2>Active Sessions</h2>\n"
        f"<p>{active_sessions} user(s) currently active</p>\n"
        "</body>\n</html>"
    )

    Path(output_path).write_text(html)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Full ETL pipeline entry point.

    1. EXTRACT — read and parse ``LOG_FILE``.
    2. TRANSFORM — compute error summary, API stats, session count.
    3. LOAD — persist aggregates to ``DB_PATH``.
    4. REPORT — write ``report.html``.
    """
    print(f"Reading log file: {LOG_FILE}")
    errors, api_calls, user_actions = extract_logs(LOG_FILE)

    print(
        f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} "
        f"(db: {DB_PATH})..."
    )

    error_summary = compute_error_summary(errors)
    api_stats = compute_api_stats(api_calls)
    active_sessions = compute_active_session_count(user_actions)

    load_to_database(DB_PATH, error_summary, api_stats)

    generate_html_report("report.html", error_summary, api_stats, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap (demo / development only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not Path(LOG_FILE).is_file():
        demo_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        Path(LOG_FILE).write_text("\n".join(demo_lines) + "\n")

    run_pipeline()