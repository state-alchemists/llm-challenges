"""
Pipeline: parse server logs, persist metrics to SQLite, and emit an HTML report.

ETL stages
~~~~~~~~~
Extract  — read ``LOG_FILE`` and extract structured records via regex.
Transform — aggregate error counts, session state, and API latency per endpoint.
Load      — write aggregated data to SQLite and render ``report.html``.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration — all read from the environment with safe defaults.
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: str = os.environ.get("PIPELINE_DB_PORT", "5432")
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """A single ERROR-level log line."""
    timestamp: str
    message: str


@dataclass
class UserRecord:
    """A single user-session INFO line."""
    timestamp: str
    user_id: str
    action: str   # e.g. "logged in" or "logged out"


@dataclass
class ApiCall:
    """A single API latency INFO line."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class AggregatedMetrics:
    """Computed aggregates produced by the Transform stage."""
    error_counts: dict[str, int]  # message → occurrences
    active_sessions: dict[str, str]  # user_id → login_timestamp
    endpoint_latencies: dict[str, list[int]]  # endpoint → [ms, ...]


class LogRecordDict(TypedDict):
    """Union of all record dicts emitted by the Extract stage."""
    pass


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

# Compiled regex patterns — compiled once at module load.
_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.*)$"
)
_RE_USER_LINE = re.compile(r"^User (?P<user_id>\S+) (?P<action>logged in|logged out)")
_RE_API_LINE = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<latency_ms>\d+)ms$"
)


def _seed_sample_log(path: Path) -> None:
    """Write minimal sample data so the pipeline has something to process."""
    sample = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    path.write_text(sample)


def extract_log_data(log_path: str) -> tuple[list[ErrorRecord], list[UserRecord], list[ApiCall]]:
    """
    Parse ``log_path`` and return three parallel lists of structured records.

    Returns
    -------
    Tuple of (errors, users, api_calls), each element already
    converted to its respective dataclass.
    """
    path = Path(log_path)

    if not path.exists():
        _seed_sample_log(path)

    errors: list[ErrorRecord] = []
    users: list[UserRecord] = []
    api_calls: list[ApiCall] = []

    for line in path.read_text().splitlines():
        m = _RE_LOG_LINE.match(line)
        if not m:
            continue

        timestamp = m.group("timestamp")
        level = m.group("level")
        rest = m.group("rest")

        if level == "ERROR":
            errors.append(ErrorRecord(timestamp=timestamp, message=rest.strip()))

        elif level == "INFO":
            user_match = _RE_USER_LINE.match(rest)
            if user_match:
                users.append(UserRecord(
                    timestamp=timestamp,
                    user_id=user_match.group("user_id"),
                    action=user_match.group("action"),
                ))
                continue

            api_match = _RE_API_LINE.match(rest)
            if api_match:
                api_calls.append(ApiCall(
                    timestamp=timestamp,
                    endpoint=api_match.group("endpoint"),
                    latency_ms=int(api_match.group("latency_ms")),
                ))

    return errors, users, api_calls


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform_data(
    errors: list[ErrorRecord],
    users: list[UserRecord],
    api_calls: list[ApiCall],
) -> AggregatedMetrics:
    """
    Aggregate raw extracted records into the shape required by the Load stage.

    - Error records are counted by message string.
    - User records update a dict of currently-active sessions.
    - API calls are grouped by endpoint for later averaging.
    """
    # Count duplicate error messages.
    error_counts: dict[str, int] = {}
    for err in errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # Track session state: user_id → login timestamp.
    # A user is "active" if we have a login record without a matching logout.
    active_sessions: dict[str, str] = {}
    for user in users:
        if user.action == "logged in":
            active_sessions[user.user_id] = user.timestamp
        elif user.action == "logged out" and user.user_id in active_sessions:
            del active_sessions[user.user_id]

    # Collect latency samples per endpoint.
    endpoint_latencies: dict[str, list[int]] = {}
    for call in api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.latency_ms)

    return AggregatedMetrics(
        error_counts=error_counts,
        active_sessions=active_sessions,
        endpoint_latencies=endpoint_latencies,
    )


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    """Create or verify the required tables."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt      TEXT,
            message TEXT,
            count   INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt       TEXT,
            endpoint TEXT,
            avg_ms   REAL
        )
        """
    )
    conn.commit()


def _build_error_counts_rows(
    metrics: AggregatedMetrics,
) -> list[tuple[str, str, int]]:
    """Prepare INSERT rows for the errors table."""
    now = datetime.datetime.now().isoformat()
    return [
        (now, msg, count)
        for msg, count in metrics.error_counts.items()
    ]


def _build_endpoint_avg_rows(
    metrics: AggregatedMetrics,
) -> list[tuple[str, str, float]]:
    """Prepare INSERT rows for api_metrics (endpoint → average latency)."""
    now = datetime.datetime.now().isoformat()
    rows: list[tuple[str, str, float]] = []
    for endpoint, latencies in metrics.endpoint_latencies.items():
        avg = sum(latencies) / len(latencies)
        rows.append((now, endpoint, avg))
    return rows


def load_to_db(db_path: str, metrics: AggregatedMetrics) -> None:
    """
    Persist aggregated metrics into the SQLite database at ``db_path``
    using **parameterized queries** (no string formatting).
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        cur = conn.cursor()

        # Insert error counts — parameterized
        for row in _build_error_counts_rows(metrics):
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                row,
            )

        # Insert API latency averages — parameterized
        for row in _build_endpoint_avg_rows(metrics):
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                row,
            )

        conn.commit()
    finally:
        conn.close()


def render_html_report(metrics: AggregatedMetrics, output_path: str) -> None:
    """
    Write ``report.html`` containing:
    - Error summary (message + occurrence count)
    - API latency table (endpoint + average ms)
    - Active session count
    """
    parts: list[str] = []

    def h(tag: str, text: str) -> None:
        parts.append(f"<{tag}>{text}</{tag}>")

    def p(text: str) -> None:
        parts.append(f"<p>{text}</p>")

    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")

    # Error Summary
    h("h1", "Error Summary")
    parts.append("<ul>")
    for msg, count in metrics.error_counts.items():
        parts.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    parts.append("</ul>")

    # API Latency table
    h("h2", "API Latency")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, latencies in metrics.endpoint_latencies.items():
        avg = sum(latencies) / len(latencies)
        parts.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    parts.append("</table>")

    # Active Sessions
    h("h2", "Active Sessions")
    p(f"{len(metrics.active_sessions)} user(s) currently active")

    parts.append("</body>")
    parts.append("</html>")

    Path(output_path).write_text("\n".join(parts))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Full ETL pipeline entry point.

    Extracts log data → transforms it → loads to DB → renders the HTML report.
    All configuration is sourced from environment variables (with safe defaults).
    """
    log_path = LOG_FILE
    db_path = DB_PATH

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # EXTRACT
    errors, users, api_calls = extract_log_data(log_path)

    # TRANSFORM
    metrics = transform_data(errors, users, api_calls)

    # LOAD — DB + HTML report
    load_to_db(db_path, metrics)
    render_html_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now().isoformat()}")


if __name__ == "__main__":
    run_pipeline()
