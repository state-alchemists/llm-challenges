#!/usr/bin/env python3
"""Log processing pipeline: extract, transform, and load server logs into a report.

Usage:
    pip install sqlite3  # stdlib, no extra install needed
    export PIPELINE_DB_PATH=metrics.db
    export PIPELINE_LOG_FILE=server.log
    python pipeline_refactored.py

Produces ``report.html`` with error summary, API latency table, and active
session count.  Also persists error aggregations and API metrics to SQLite.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional


# ===========================================================================
# Configuration
# ===========================================================================


@dataclass
class PipelineConfig:
    """Runtime parameters sourced from environment variables.

    Every field has a sensible default so the script can run out of the box
    with no configuration.
    """

    db_path: str
    log_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> PipelineConfig:
    """Build config from environment variables, falling back to defaults."""
    return PipelineConfig(
        db_path=os.environ.get("PIPELINE_DB_PATH", "metrics.db"),
        log_path=os.environ.get("PIPELINE_LOG_FILE", "server.log"),
        db_host=os.environ.get("PIPELINE_DB_HOST", "localhost"),
        db_port=int(os.environ.get("PIPELINE_DB_PORT", "5432")),
        db_user=os.environ.get("PIPELINE_DB_USER", "admin"),
        db_pass=os.environ.get("PIPELINE_DB_PASS", ""),
    )


# ===========================================================================
# Extract — parse log file into structured records
# ===========================================================================

_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<payload>.*)$"
)
_USER_RE = re.compile(r"^User (\S+) (.+)$")
_API_RE = re.compile(r"^API (\S+?)(?: took (\d+)ms)?$")


@dataclass
class ErrorRecord:
    """A single ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class UserRecord:
    """An INFO-level log line recording a user login or logout."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiRecord:
    """An INFO-level log line recording an API call's duration."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarnRecord:
    """A single WARN-level log line (collected but not included in the report)."""

    timestamp: str
    message: str


LogRecord = ErrorRecord | UserRecord | ApiRecord | WarnRecord


def parse_log_line(line: str) -> Optional[LogRecord]:
    """Parse one log line into a structured record using regex.

    Supports four line types:

    * ``YYYY-MM-DD HH:MM:SS ERROR <message>``
    * ``YYYY-MM-DD HH:MM:SS WARN <message>``
    * ``YYYY-MM-DD HH:MM:SS INFO User <id> <action>``
    * ``YYYY-MM-DD HH:MM:SS INFO API <endpoint> [took <N>ms]``

    Returns ``None`` when the line does not match any known pattern.
    """
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None

    ts: str = m.group("ts")
    level: str = m.group("level")
    payload: str = m.group("payload")

    if level == "ERROR":
        return ErrorRecord(timestamp=ts, message=payload)
    if level == "WARN":
        return WarnRecord(timestamp=ts, message=payload)

    # INFO — try user event first, then API call.
    if level == "INFO":
        user_m = _USER_RE.match(payload)
        if user_m:
            return UserRecord(
                timestamp=ts,
                user_id=user_m.group(1),
                action=user_m.group(2),
            )
        api_m = _API_RE.match(payload)
        if api_m:
            duration = int(api_m.group(2)) if api_m.group(2) else 0
            return ApiRecord(
                timestamp=ts,
                endpoint=api_m.group(1),
                duration_ms=duration,
            )

    return None


def _update_sessions(
    record: LogRecord,
    sessions: dict[str, str],
) -> None:
    """Mutate *sessions* in-place based on a user login/logout event."""
    if not isinstance(record, UserRecord):
        return
    action_lower = record.action.lower()
    if "logged in" in action_lower:
        sessions[record.user_id] = record.timestamp
    elif "logged out" in action_lower:
        sessions.pop(record.user_id, None)


@dataclass
class ExtractResult:
    """Structured data produced by the **extract** phase."""

    errors: list[ErrorRecord]
    api_calls: list[ApiRecord]
    active_sessions: dict[str, str]


def extract_logs(log_path: str) -> ExtractResult:
    """Read *log_path*, parse every line, and return structured records.

    Session state (login / logout) is tracked during extraction so the caller
    can query the final set of active sessions.
    """
    errors: list[ErrorRecord] = []
    api_calls: list[ApiRecord] = []
    sessions: dict[str, str] = {}

    if not os.path.exists(log_path):
        return ExtractResult(errors=errors, api_calls=api_calls, active_sessions=sessions)

    with open(log_path, "r") as f:
        for line in f:
            stripped = line.rstrip("\n")
            record = parse_log_line(stripped)
            if record is None:
                continue
            _update_sessions(record, sessions)
            if isinstance(record, ErrorRecord):
                errors.append(record)
            elif isinstance(record, ApiRecord):
                api_calls.append(record)

    return ExtractResult(
        errors=errors,
        api_calls=api_calls,
        active_sessions=sessions,
    )


# ===========================================================================
# Transform — aggregate parsed records into report data
# ===========================================================================


@dataclass
class TransformResult:
    """Aggregated data produced by the **transform** phase."""

    error_counts: dict[str, int]
    endpoint_times_ms: dict[str, list[int]]
    active_session_count: int


def aggregate_errors(errors: list[ErrorRecord]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def aggregate_api_latency(calls: list[ApiRecord]) -> dict[str, list[int]]:
    """Group API call durations by endpoint."""
    groups: dict[str, list[int]] = {}
    for call in calls:
        groups.setdefault(call.endpoint, []).append(call.duration_ms)
    return groups


def transform(extracted: ExtractResult) -> TransformResult:
    """Run all aggregations over extracted data.

    Returns error counts, endpoint latency groups, and the number of
    sessions still active at the end of the log.
    """
    return TransformResult(
        error_counts=aggregate_errors(extracted.errors),
        endpoint_times_ms=aggregate_api_latency(extracted.api_calls),
        active_session_count=len(extracted.active_sessions),
    )


# ===========================================================================
# Load — persist to database and generate HTML report
# ===========================================================================


def init_database(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure tables exist.

    Returns an open connection; the caller is responsible for closing it.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def persist_error_summary(
    conn: sqlite3.Connection,
    error_counts: dict[str, int],
    run_ts: str,
) -> None:
    """Insert error aggregation rows with a parameterized query."""
    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (run_ts, msg, count),
        )


def persist_api_metrics(
    conn: sqlite3.Connection,
    endpoint_times_ms: dict[str, list[int]],
    run_ts: str,
) -> None:
    """Insert per-endpoint average-latency rows with a parameterized query."""
    for ep, times in endpoint_times_ms.items():
        avg_ms = sum(times) / len(times)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (run_ts, ep, avg_ms),
        )


def build_report_html(
    error_counts: dict[str, int],
    endpoint_times_ms: dict[str, list[int]],
    active_session_count: int,
) -> str:
    """Build the HTML report string.

    Sections:
    1. Error summary — bullet list with occurrence counts.
    2. API latency — table of endpoint / average response time.
    3. Active sessions — count of users still logged in.
    """
    parts: list[str] = [
        "<html>\n<head><title>System Report</title></head>\n<body>\n",
        "<h1>Error Summary</h1>\n<ul>\n",
    ]
    for err_msg, count in sorted(error_counts.items()):
        parts.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>\n")
    parts.append("</ul>\n")

    parts.append("<h2>API Latency</h2>\n<table border='1'>\n")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n")
    for ep, times in sorted(endpoint_times_ms.items()):
        avg = sum(times) / len(times)
        parts.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n")
    parts.append("</table>\n")

    parts.append("<h2>Active Sessions</h2>\n")
    parts.append(f"<p>{active_session_count} user(s) currently active</p>\n")
    parts.append("</body>\n</html>")

    return "".join(parts)


def write_report(html: str, path: str = "report.html") -> None:
    """Write *html* to *path*."""
    with open(path, "w") as f:
        f.write(html)


# ===========================================================================
# Orchestrator
# ===========================================================================


def main() -> None:
    """Run the full ETL pipeline: extract → transform → load.

    Reads ``PIPELINE_LOG_FILE`` (default: ``server.log``), parses every line,
    aggregates errors and API metrics, persists results to the SQLite
    database at ``PIPELINE_DB_PATH`` (default: ``metrics.db``), and writes
    ``report.html``.
    """
    config = load_config()

    # Announce the connection target (preserves original output behaviour).
    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )

    # --- Extract ---
    extracted = extract_logs(config.log_path)

    # --- Transform ---
    transformed = transform(extracted)

    # --- Load (DB) ---
    run_ts = str(datetime.datetime.now())
    conn = init_database(config.db_path)
    try:
        persist_error_summary(conn, transformed.error_counts, run_ts)
        persist_api_metrics(conn, transformed.endpoint_times_ms, run_ts)
        conn.commit()
    finally:
        conn.close()

    # --- Load (report) ---
    html = build_report_html(
        transformed.error_counts,
        transformed.endpoint_times_ms,
        transformed.active_session_count,
    )
    write_report(html)

    print(f"Job finished at {run_ts}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    config = load_config()
    if not os.path.exists(config.log_path):
        with open(config.log_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
