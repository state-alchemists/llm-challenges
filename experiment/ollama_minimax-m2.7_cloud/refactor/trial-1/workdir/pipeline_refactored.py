"""
Server log processing pipeline — ETL pattern.

Extracts structured data from server logs, aggregates metrics, persists to
SQLite, and generates an HTML report.

Usage:
    export DB_PATH="metrics.db"
    export LOG_FILE="server.log"
    export DB_HOST="localhost"
    export DB_PORT="5432"
    export DB_USER="admin"
    export DB_PASS="secret"
    python pipeline_refactored.py
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Dict, List, NamedTuple


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ErrorEntry(NamedTuple):
    """A single ERROR-level log line, parsed."""
    dt: str
    message: str


class SessionEvent(NamedTuple):
    """User session activity."""
    dt: str
    uid: str
    action: str  # "logged in" | "logged out"


class ApiCall(NamedTuple):
    """A single API latency record."""
    dt: str
    endpoint: str
    ms: int


class WarnEntry(NamedTuple):
    """A single WARN-level log line, parsed."""
    dt: str
    message: str


# ---------------------------------------------------------------------------
# Regex patterns (compiled once)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_RE_API = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)
_RE_WARN = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.+)$"
)


# ---------------------------------------------------------------------------
# EXTRACT — read and parse the log file
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: str) -> tuple[list[ErrorEntry], list[SessionEvent], list[ApiCall], list[WarnEntry]]:
    """
    Read ``log_path`` and emit four parallel lists of structured log entries.

    Returns
    -------
    Tuple of (errors, sessions, api_calls, warnings)
    """
    errors: list[ErrorEntry] = []
    sessions: list[SessionEvent] = []
    api_calls: list[ApiCall] = []
    warnings: list[WarnEntry] = []

    if not os.path.exists(log_path):
        return errors, sessions, api_calls, warnings

    with open(log_path, "r") as fh:
        for raw in fh:
            line = raw.rstrip("\n")

            m = _RE_ERROR.match(line)
            if m:
                errors.append(ErrorEntry(dt=m.group("dt"), message=m.group("message")))
                continue

            m = _RE_USER.match(line)
            if m:
                sessions.append(SessionEvent(
                    dt=m.group("dt"),
                    uid=m.group("uid"),
                    action=m.group("action"),
                ))
                continue

            m = _RE_API.match(line)
            if m:
                api_calls.append(ApiCall(
                    dt=m.group("dt"),
                    endpoint=m.group("endpoint"),
                    ms=int(m.group("ms")),
                ))
                continue

            m = _RE_WARN.match(line)
            if m:
                warnings.append(WarnEntry(dt=m.group("dt"), message=m.group("message")))
                continue

    return errors, sessions, api_calls, warnings


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate raw entries into metrics
# ---------------------------------------------------------------------------

def aggregate_errors(errors: list[ErrorEntry]) -> Dict[str, int]:
    """
    Count occurrences of each unique error message.

    Returns
    -------
    Dict mapping error message -> count
    """
    counts: Dict[str, int] = {}
    for e in errors:
        counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def aggregate_api_latency(api_calls: list[ApiCall]) -> Dict[str, list[int]]:
    """
    Group API calls by endpoint, preserving individual latency values.

    Returns
    -------
    Dict mapping endpoint -> list of latency measurements (ms)
    """
    stats: Dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.ms)
    return stats


def compute_avg_latency(latency_by_endpoint: Dict[str, list[int]]) -> Dict[str, float]:
    """
    Compute the average latency per endpoint.

    Returns
    -------
    Dict mapping endpoint -> average latency (ms), rounded to 1 decimal
    """
    return {
        ep: round(sum(times) / len(times), 1)
        for ep, times in latency_by_endpoint.items()
    }


def track_active_sessions(sessions: list[SessionEvent]) -> int:
    """
    Walk session events in chronological order and return the count of
    users currently logged in after processing all events.

    A user starts a session on "logged in" and ends it on "logged out".
    Users who never log out remain counted as active.
    """
    active: Dict[str, str] = {}  # uid -> login_dt
    for event in sessions:
        if "logged in" in event.action:
            active[event.uid] = event.dt
        elif "logged out" in event.action:
            active.pop(event.uid, None)
    return len(active)


# ---------------------------------------------------------------------------
# LOAD — persist to SQLite and emit the HTML report
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_metrics(
    conn: sqlite3.Connection,
    error_counts: Dict[str, int],
    avg_latency: Dict[str, float],
) -> None:
    """
    Persist aggregated error counts and API latency averages to SQLite.

    Uses parameterised queries to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg_ms in avg_latency.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()


def generate_html_report(
    error_counts: Dict[str, int],
    avg_latency: Dict[str, float],
    active_session_count: int,
    output_path: str = "report.html",
) -> None:
    """
    Write ``report.html`` with error summary, API latency table, and
    active session count.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if error_counts:
        for msg, count in error_counts.items():
            lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    else:
        lines.append("<li>No errors recorded</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if avg_latency:
        for ep, avg_ms in avg_latency.items():
            lines.append(f"<tr><td>{ep}</td><td>{avg_ms}</td></tr>")
    else:
        lines.append("<tr><td colspan='2'>No API calls recorded</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline:

    1. EXTRACT — parse log lines into structured records
    2. TRANSFORM — aggregate errors, latency, and session counts
    3. LOAD — write SQLite tables and emit ``report.html``
    """
    # EXTRACT
    errors, sessions, api_calls, _ = extract_log_entries(LOG_FILE)

    # TRANSFORM
    error_counts = aggregate_errors(errors)
    latency_by_endpoint = aggregate_api_latency(api_calls)
    avg_latency = compute_avg_latency(latency_by_endpoint)
    active_count = track_active_sessions(sessions)

    # LOAD
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    load_metrics(conn, error_counts, avg_latency)
    conn.close()

    generate_html_report(error_counts, avg_latency, active_count)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
