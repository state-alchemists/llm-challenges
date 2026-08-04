"""
Log processing pipeline that extracts metrics from server logs and generates an HTML report.

Environment variables:
    DB_PATH      — path to the SQLite database (default: metrics.db)
    LOG_FILE     — path to the server log file (default: server.log)
    DB_HOST      — database host (default: localhost)
    DB_PORT      — database port (default: 5432)
    DB_USER      — database username (default: admin)
    DB_PASS      — database password (default: password123)
    REPORT_PATH  — path for the output HTML report (default: report.html)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")
REPORT_PATH = os.environ.get("REPORT_PATH", "report.html")


# --------------------------------------------------------------------------- #
# Data structures                                                             #
# --------------------------------------------------------------------------- #

class LogEntry(NamedTuple):
    """A parsed log line."""
    timestamp: str
    level: str
    message: str


class ErrorRecord(NamedTuple):
    """An aggregated error with an occurrence count."""
    message: str
    occurrences: int


class ApiMetric(NamedTuple):
    """An API endpoint with its average latency."""
    endpoint: str
    avg_ms: float


class SessionEvent(NamedTuple):
    """A user session lifecycle event."""
    user_id: str
    action: str
    timestamp: str


# --------------------------------------------------------------------------- #
# EXTRACT — read and parse log lines                                          #
# --------------------------------------------------------------------------- #

# ISO-like timestamp: 2024-01-01 12:00:00
_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

# Level word
_LEVEL_RE = re.compile(r"\b(INFO|ERROR|WARN)\b")

# User lifecycle: User <id> logged in|out
_USER_SESSION_RE = re.compile(r"User\s+(\S+)\s+(logged in|logged out)")

# API call: API /<endpoint> took <N>ms
_API_LATENCY_RE = re.compile(r"API\s+(\S+)\s+took\s+(\d+)\s*ms")


def read_log_lines(path: str) -> list[str]:
    """
    Read all lines from *path*. Silently returns an empty list if the file
    does not exist.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        return fh.readlines()


def parse_log_line(line: str) -> LogEntry | None:
    """
    Parse a single log line into a LogEntry.

    Expected format:  <timestamp> <level> <rest of message>
    Returns None if the line doesn't match the expected structure.
    """
    ts_match = _TIMESTAMP_RE.match(line)
    if not ts_match:
        return None

    timestamp = ts_match.group(1)
    remainder = line[ts_match.end() :].strip()

    level_match = _LEVEL_RE.search(remainder)
    if not level_match:
        return None

    level = level_match.group(1)
    message = remainder[level_match.end() :].strip()

    return LogEntry(timestamp=timestamp, level=level, message=message)


def extract_sessions(lines: list[str]) -> dict[str, str]:
    """
    Scan *lines* for user login/logout events and return a dict of currently
    active sessions: {user_id: last_seen_timestamp}.

    A user is considered active from their login until their logout.
    """
    sessions: dict[str, str] = {}
    for line in lines:
        entry = parse_log_line(line)
        if not entry or entry.level != "INFO":
            continue
        user_match = _USER_SESSION_RE.search(entry.message)
        if not user_match:
            continue
        uid, action = user_match.group(1), user_match.group(2)
        if action == "logged in":
            sessions[uid] = entry.timestamp
        elif action == "logged out" and uid in sessions:
            del sessions[uid]
    return sessions


def extract_api_calls(lines: list[str]) -> list[tuple[str, str, int]]:
    """
    Return a list of (timestamp, endpoint, latency_ms) tuples from INFO
    lines that mention the API latency pattern.
    """
    records: list[tuple[str, str, int]] = []
    for line in lines:
        entry = parse_log_line(line)
        if not entry or entry.level != "INFO":
            continue
        api_match = _API_LATENCY_RE.search(entry.message)
        if api_match:
            endpoint = api_match.group(1)
            latency_ms = int(api_match.group(2))
            records.append((entry.timestamp, endpoint, latency_ms))
    return records


def extract_errors(lines: list[str]) -> list[tuple[str, str]]:
    """
    Return a list of (timestamp, error_message) tuples from ERROR lines.
    """
    records: list[tuple[str, str]] = []
    for line in lines:
        entry = parse_log_line(line)
        if entry and entry.level == "ERROR":
            records.append((entry.timestamp, entry.message))
    return records


# --------------------------------------------------------------------------- #
# TRANSFORM — aggregate raw records into summary statistics                   #
# --------------------------------------------------------------------------- #

def build_error_summary(errors: list[tuple[str, str]]) -> list[ErrorRecord]:
    """
    Count occurrences of each distinct error message and return them sorted
    descending by count.
    """
    counts: dict[str, int] = {}
    for _, msg in errors:
        counts[msg] = counts.get(msg, 0) + 1
    return sorted(
        [ErrorRecord(message=msg, occurrences=cnt) for msg, cnt in counts.items()],
        key=lambda r: r.occurrences,
        reverse=True,
    )


def build_api_metrics(calls: list[tuple[str, str, int]]) -> list[ApiMetric]:
    """
    Compute average latency per endpoint and return a sorted list.
    """
    by_endpoint: dict[str, list[int]] = {}
    for _, endpoint, ms in calls:
        by_endpoint.setdefault(endpoint, []).append(ms)

    metrics: list[ApiMetric] = []
    for ep, times in by_endpoint.items():
        avg = sum(times) / len(times)
        metrics.append(ApiMetric(endpoint=ep, avg_ms=avg))

    return sorted(metrics, key=lambda m: m.endpoint)


# --------------------------------------------------------------------------- #
# LOAD — write aggregated data to the DB and render the HTML report           #
# --------------------------------------------------------------------------- #

def init_db(conn: sqlite3.Connection) -> None:
    """Create the metrics tables if they do not already exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_errors(conn: sqlite3.Connection, errors: list[ErrorRecord]) -> None:
    """
    Persist error summary rows using a parameterized INSERT to prevent SQL
    injection.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.executemany(
        "INSERT INTO errors VALUES (?, ?, ?)",
        [(now, rec.message, rec.occurrences) for rec in errors],
    )


def load_api_metrics(conn: sqlite3.Connection, metrics: list[ApiMetric]) -> None:
    """
    Persist API metric rows using a parameterized INSERT to prevent SQL
    injection.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.executemany(
        "INSERT INTO api_metrics VALUES (?, ?, ?)",
        [(now, m.endpoint, m.avg_ms) for m in metrics],
    )


def render_report(
    errors: list[ErrorRecord],
    api_metrics: list[ApiMetric],
    active_session_count: int,
    output_path: str,
) -> None:
    """
    Render the HTML report covering error summary, API latency table, and
    active session count.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for rec in errors:
        lines.append(
            f"<li><b>{rec.message}</b>: {rec.occurrences} occurrences</li>"
        )

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for m in api_metrics:
        lines.append(
            f"<tr><td>{m.endpoint}</td><td>{round(m.avg_ms, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    Path(output_path).write_text("\n".join(lines))


# --------------------------------------------------------------------------- #
# Main pipeline                                                                #
# --------------------------------------------------------------------------- #

def run_pipeline() -> None:
    """
    Entry point: Extract → Transform → Load.

    Reads ``LOG_FILE``, aggregates errors and API latencies, writes the
    results to ``DB_PATH`` and produces ``REPORT_PATH``.
    """
    print(f"Reading log file: {LOG_FILE}")
    raw_lines = read_log_lines(LOG_FILE)

    print(
        f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}..."
    )

    # EXTRACT
    errors = extract_errors(raw_lines)
    api_calls = extract_api_calls(raw_lines)
    sessions = extract_sessions(raw_lines)

    # TRANSFORM
    error_summary = build_error_summary(errors)
    api_metrics = build_api_metrics(api_calls)
    active_count = len(sessions)

    # LOAD — SQLite
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        load_errors(conn, error_summary)
        load_api_metrics(conn, api_metrics)
        conn.commit()
    finally:
        conn.close()

    # LOAD — HTML report
    print(f"Writing report to: {REPORT_PATH}")
    render_report(error_summary, api_metrics, active_count, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a minimal sample log when no log file exists so the pipeline
    # can run end-to-end out of the box.
    if not os.path.exists(LOG_FILE):
        sample_lines = (
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        Path(LOG_FILE).write_text(sample_lines)

    run_pipeline()
