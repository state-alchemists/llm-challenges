"""
Log processing pipeline: extract → transform → load → report.

Reads server logs, stores aggregated metrics in SQLite, and produces an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (all sourced from environment variables with safe defaults)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """A single error entry extracted from a log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class ApiCallRecord:
    """A single API call entry extracted from a log line."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class UserActionRecord:
    """A single user-session action extracted from a log line."""

    timestamp: str
    user_id: str
    action: str


# Internal accumulator for session state
@dataclass
class SessionState:
    """Tracks currently active user sessions (user_id → login timestamp)."""

    active: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load for performance)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(r"^\S+ \S+ ERROR (.+)$")
_RE_WARN = re.compile(r"^\S+ \S+ WARN (.+)$")
_RE_USER_ACTION = re.compile(r"^\S+ \S+ INFO User (\S+) (logged in|logged out)")
_RE_API_CALL = re.compile(r"^\S+ \S+ INFO API (\S+) took (\d+)ms")


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> tuple[ErrorRecord | None, ApiCallRecord | None, UserActionRecord | None]:
    """
    Parse a single log line and return the appropriate record(s).

    Returns a 3-tuple of (error, api_call, user_action); each slot is None
    when the line doesn't match that pattern.

    Log format::

        2024-01-01 12:00:00 LEVEL message

    Examples::

        2024-01-01 12:05:00 ERROR Database timeout
        2024-01-01 12:00:00 INFO User 42 logged in
        2024-01-01 12:08:00 INFO API /users/profile took 250ms
    """
    error: ErrorRecord | None = None
    api_call: ApiCallRecord | None = None
    user_action: UserActionRecord | None = None

    if (m := _RE_ERROR.match(line)) is not None:
        error = ErrorRecord(timestamp=_timestamp(line), message=m.group(1))
    elif (m := _RE_WARN.match(line)) is not None:
        # Warnings are tracked as errors for aggregation purposes
        error = ErrorRecord(timestamp=_timestamp(line), message=m.group(1))
    elif (m := _RE_USER_ACTION.match(line)) is not None:
        user_action = UserActionRecord(
            timestamp=_timestamp(line),
            user_id=m.group(1),
            action=m.group(2),
        )
    elif (m := _RE_API_CALL.match(line)) is not None:
        api_call = ApiCallRecord(
            timestamp=_timestamp(line),
            endpoint=m.group(1),
            duration_ms=int(m.group(2)),
        )

    return error, api_call, user_action


def _timestamp(line: str) -> str:
    """Extract the ISO-style timestamp prefix from a log line."""
    return line[:19]


def read_log_file(path: str | Path) -> tuple[list[ErrorRecord], list[ApiCallRecord], SessionState]:
    """
    Read and parse every line in *path*.

    Returns a 3-tuple of:
      - list of ErrorRecord
      - list of ApiCallRecord
      - SessionState (mutated in-place to track active sessions)
    """
    errors: list[ErrorRecord] = []
    api_calls: list[ApiCallRecord] = []
    sessions = SessionState()

    file_path = Path(path)
    if not file_path.is_file():
        print(f"Log file not found: {file_path}", file=sys.stderr)
        return errors, api_calls, sessions

    with file_path.open() as fh:
        for line in fh:
            error, api_call, user_action = parse_log_line(line)

            if error is not None:
                errors.append(error)

            if api_call is not None:
                api_calls.append(api_call)

            if user_action is not None:
                if user_action.action == "logged in":
                    sessions.active[user_action.user_id] = user_action.timestamp
                elif user_action.action == "logged out" and user_action.user_id in sessions.active:
                    del sessions.active[user_action.user_id]

    return errors, api_calls, sessions


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ErrorRecord]) -> dict[str, int]:
    """
    Count occurrences of each unique error message.

    Returns a dict mapping error message → occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def compute_api_stats(api_calls: list[ApiCallRecord]) -> dict[str, float]:
    """
    Compute average latency per API endpoint.

    Returns a dict mapping endpoint → average duration in milliseconds.
    """
    buckets: dict[str, list[int]] = {}
    for call in api_calls:
        buckets.setdefault(call.endpoint, []).append(call.duration_ms)

    return {ep: sum(times) / len(times) for ep, times in buckets.items()}


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """Create metric tables if they do not exist."""
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def store_error_counts(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Write aggregated error counts into the ``errors`` table.

    Uses a parameterized INSERT to prevent SQL injection.
    """
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.executemany(
        "INSERT INTO errors VALUES (?, ?, ?)",
        [(now, msg, count) for msg, count in error_counts.items()],
    )
    conn.commit()


def store_api_metrics(conn: sqlite3.Connection, api_stats: dict[str, float]) -> None:
    """
    Write per-endpoint average latencies into the ``api_metrics`` table.

    Uses a parameterized INSERT to prevent SQL injection.
    """
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.executemany(
        "INSERT INTO api_metrics VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in api_stats.items()],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------


def generate_html_report(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    active_session_count: int,
    output_path: str | Path = "report.html",
) -> None:
    """
    Write the HTML report covering error summary, API latency table,
    and active session count.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in api_stats.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    Path(output_path).write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# PIPELINE ORCHESTRATION
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full extract → transform → load → report pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # EXTRACT
    errors, api_calls, sessions = read_log_file(LOG_FILE)

    # TRANSFORM
    error_counts = aggregate_errors(errors)
    api_stats = compute_api_stats(api_calls)

    # LOAD (SQLite)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    store_error_counts(conn, error_counts)
    store_api_metrics(conn, api_stats)
    conn.close()

    # REPORT
    generate_html_report(error_counts, api_stats, len(sessions.active))

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bootstrap a minimal sample log when the file is absent (preserves original behaviour)
    if not Path(LOG_FILE).is_file():
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        Path(LOG_FILE).write_text("\n".join(sample_lines) + "\n")

    run_pipeline()