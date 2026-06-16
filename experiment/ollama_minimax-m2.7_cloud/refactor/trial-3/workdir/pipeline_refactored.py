"""
Pipeline: parse server logs, persist metrics to SQLite, emit an HTML report.

ETL layout:
  extract  — read and parse log lines with regex
  transform — aggregate errors, session state, API latency
  load     — write to SQLite (parameterized) and render report.html
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
# Configuration  (all from environment, with safe defaults for local dev)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")  # empty default; set via env


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str


@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class SessionEvent:
    timestamp: str
    user_id: str
    action: str  # "logged in" | "logged out"


# Stored after transform
@dataclass
class ErrorBucket:
    message: str
    count: int


@dataclass
class EndpointLatency:
    endpoint: str
    avg_ms: float


@dataclass
class PipelineData:
    errors: list[ErrorBucket] = field(default_factory=list)
    sessions_active: int = 0
    api_latency: list[EndpointLatency] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns  (module-level for efficiency)
# ---------------------------------------------------------------------------

# Format: "2024-01-01 12:00:00 INFO ...", "2024-01-01 12:00:00 ERROR ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<message>.*)$"
)

# INFO line with User activity
_USER_ACTION_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>logged in|logged out)$")

# INFO line with API timing: "API /foo/bar took 123ms"
_API_Timing_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$")


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def extract(
    log_path: str,
    *,
    _user_re: re.Pattern[str] = _USER_ACTION_RE,
    _api_re: re.Pattern[str] = _API_Timing_RE,
) -> tuple[list[LogEntry], list[ApiCall], list[SessionEvent]]:
    """
    Parse ``log_path`` line by line.

    Returns:
        (log_entries, api_calls, session_events)
    """
    log_entries: list[LogEntry] = []
    api_calls: list[ApiCall] = []
    session_events: list[SessionEvent] = []

    if not os.path.exists(log_path):
        return log_entries, api_calls, session_events

    with open(log_path, "r") as fh:
        for raw in fh:
            m = _LOG_LINE_RE.match(raw)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            payload = m.group("message")

            if level == "INFO" and "User" in payload:
                um = _user_re.match(payload)
                if um:
                    session_events.append(
                        SessionEvent(
                            timestamp=timestamp,
                            user_id=um.group("user_id"),
                            action=um.group("action"),
                        )
                    )
                # INFO lines that mention "User" but don't match the
                # logged-in/out pattern are ignored (no spec for them).
                continue

            if level == "INFO" and "API" in payload:
                am = _api_re.search(payload)
                if am:
                    api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=am.group("endpoint"),
                            duration_ms=int(am.group("ms")),
                        )
                    )
                continue

            if level in ("ERROR", "WARN"):
                log_entries.append(LogEntry(timestamp=timestamp, level=level, message=payload))

    return log_entries, api_calls, session_events


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform(
    log_entries: list[LogEntry],
    api_calls: list[ApiCall],
    session_events: list[SessionEvent],
) -> PipelineData:
    """
    Aggregate raw extracted data into the summary structures needed for load.

    - Errors are bucketed by exact message text and counted.
    - Active sessions are tracked via a dict; a user logged out removes them.
    - API calls are averaged per endpoint.
    """
    # --- errors ---
    error_counts: dict[str, int] = {}
    for entry in log_entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    errors = [ErrorBucket(message=msg, count=cnt) for msg, cnt in error_counts.items()]

    # --- sessions ---
    active_sessions: dict[str, str] = {}  # uid -> login timestamp
    for ev in session_events:
        if ev.action == "logged in":
            active_sessions[ev.user_id] = ev.timestamp
        elif ev.action == "logged out" and ev.user_id in active_sessions:
            del active_sessions[ev.user_id]

    # --- API latency per endpoint ---
    endpoint_times: dict[str, list[int]] = {}
    for call in api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.duration_ms)

    api_latency = [
        EndpointLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in endpoint_times.items()
    ]

    return PipelineData(
        errors=errors,
        sessions_active=len(active_sessions),
        api_latency=api_latency,
    )


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def _write_errors(conn: sqlite3.Connection, errors: list[ErrorBucket]) -> None:
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for eb in errors:
        # Parameterized — no string formatting, no injection risk.
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, eb.message, eb.count),
        )
    conn.commit()


def _write_api_metrics(conn: sqlite3.Connection, latency: list[EndpointLatency]) -> None:
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for ep in latency:
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep.endpoint, ep.avg_ms),
        )
    conn.commit()


def _render_html(
    errors: list[ErrorBucket],
    api_latency: list[EndpointLatency],
    sessions_active: int,
) -> str:
    """Build the HTML report string."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    out = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        f"<p><i>Generated {now}</i></p>\n"
        "<h1>Error Summary</h1>\n"
    )

    if errors:
        out += "<ul>\n"
        for eb in errors:
            out += f"<li><b>{eb.message}</b>: {eb.count} occurrence(s)</li>\n"
        out += "</ul>\n"
    else:
        out += "<p>No errors recorded.</p>\n"

    out += "<h2>API Latency</h2>\n"
    if api_latency:
        out += (
            "<table border='1'>\n"
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        )
        for ep in api_latency:
            out += (
                f"<tr><td>{ep.endpoint}</td>"
                f"<td>{round(ep.avg_ms, 1)}</td></tr>\n"
            )
        out += "</table>\n"
    else:
        out += "<p>No API calls recorded.</p>\n"

    out += (
        "<h2>Active Sessions</h2>\n"
        f"<p>{sessions_active} user(s) currently active</p>\n"
        "</body>\n"
        "</html>"
    )
    return out


def load(
    db_path: str,
    data: PipelineData,
    report_path: str = "report.html",
    *,
    _log_fn=print,
) -> None:
    """
    Persist ``data`` to SQLite and write ``report_path`` as HTML.

    Args:
        db_path:     Path to the SQLite database file.
        data:        Aggregated pipeline data from ``transform``.
        report_path: Destination for the HTML report.
        _log_fn:     Injectable logger for testability.
    """
    _log_fn(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    conn = sqlite3.connect(db_path)
    try:
        _ensure_tables(conn)
        _write_errors(conn, data.errors)
        _write_api_metrics(conn, data.api_latency)
    finally:
        conn.close()

    html = _render_html(data.errors, data.api_latency, data.sessions_active)
    Path(report_path).write_text(html, encoding="utf-8")

    _log_fn(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def run_pipeline(
    log_file: str = LOG_FILE,
    db_path: str = DB_PATH,
    report_path: str = "report.html",
) -> None:
    """
    Run the full ETL pipeline.

    Args:
        log_file:    Path to the server log file.
        db_path:     Path to the SQLite database.
        report_path: Destination for the HTML report.
    """
    log_entries, api_calls, session_events = extract(log_file)
    data = transform(log_entries, api_calls, session_events)
    load(db_path, data, report_path)


# ---------------------------------------------------------------------------
# BOOTSTRAP (dev / demo)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
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