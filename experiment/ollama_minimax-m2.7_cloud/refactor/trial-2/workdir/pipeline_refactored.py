"""
Log processing pipeline — ETL for server logs.

Extracts entries from a log file, transforms them into metrics, and loads
the results into a SQLite database plus an HTML report.

Environment variables:
    DB_PATH       — Path to the SQLite database (default: metrics.db)
    LOG_FILE      — Path to the server log file (default: server.log)
    DB_HOST       — Database host (unused placeholder; kept for compatibility)
    DB_PORT       — Database port (unused placeholder)
    DB_USER       — Database username (unused placeholder)
    DB_PASS       — Database password (unused placeholder — never hardcode)
    REPORT_PATH   — Path for the HTML output (default: report.html)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from datetime import UTC
from typing import TypedDict


# ----------------------------------------------------------------------------- #
# Types
# ----------------------------------------------------------------------------- #

class LogEntry(TypedDict):
    """A parsed log line with structured fields."""
    timestamp: str
    level: str
    message: str


class ErrorEntry(TypedDict):
    """Error record with message and count."""
    message: str
    count: int


class ApiMetric(TypedDict):
    """Aggregated API call latency record."""
    endpoint: str
    avg_ms: float


# ----------------------------------------------------------------------------- #
# Extract
# ----------------------------------------------------------------------------- #

# Regex patterns for log line parsing
_TIMESTAMP_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<message>.*)$"
)

_USER_ACTION_RE = re.compile(
    r"^User (?P<uid>\S+) (?P<action>logged in|logged out)$"
)

_API_CALL_RE = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


def extract_log_entries(log_path: str) -> list[LogEntry]:
    """
    Read and parse all log entries from *log_path*.

    Each line must match the pattern:
        YYYY-MM-DD HH:MM:SS LEVEL message

    Returns a list of LogEntry dicts.
    """
    entries: list[LogEntry] = []
    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _TIMESTAMP_RE.match(line)
            if m is None:
                continue
            entries.append(LogEntry(
                timestamp=m.group("timestamp"),
                level=m.group("level"),
                message=m.group("message"),
            ))
    return entries


# ----------------------------------------------------------------------------- #
# Transform
# ----------------------------------------------------------------------------- #

class TransformationResult(TypedDict):
    """Structured output from the transform step."""
    errors: dict[str, int]
    api_stats: dict[str, list[int]]
    active_sessions: dict[str, str]


def transform_entries(entries: list[LogEntry]) -> TransformationResult:
    """
    Classify *entries* into:
      - error counts (keyed by message)
      - per-endpoint API latency lists
      - active session map (user_id -> login_timestamp)

    Sessions with a matching "logged out" entry are removed.
    """
    errors: dict[str, int] = defaultdict(int)
    api_stats: dict[str, list[int]] = defaultdict(list)
    sessions: dict[str, str] = {}

    for entry in entries:
        msg = entry["message"]

        if entry["level"] == "ERROR":
            errors[msg] += 1

        elif entry["level"] == "INFO":
            user_m = _USER_ACTION_RE.match(msg)
            if user_m:
                uid = user_m.group("uid")
                action = user_m.group("action")
                if action == "logged in":
                    sessions[uid] = entry["timestamp"]
                elif action == "logged out" and uid in sessions:
                    sessions.pop(uid)
                continue

            api_m = _API_CALL_RE.match(msg)
            if api_m:
                endpoint = api_m.group("endpoint")
                ms = int(api_m.group("ms"))
                api_stats[endpoint].append(ms)

    return TransformationResult(
        errors=dict(errors),
        api_stats=dict(api_stats),
        active_sessions=sessions,
    )


# ----------------------------------------------------------------------------- #
# Load
# ----------------------------------------------------------------------------- #

def ensure_schema(conn: sqlite3.Connection) -> None:
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
    db_path: str,
    errors: dict[str, int],
    api_stats: dict[str, list[int]],
    timestamp: str | None = None,
) -> None:
    """
    Insert aggregated *errors* and *api_stats* into the SQLite database
    at *db_path* using parameterized queries.

    *timestamp* defaults to the current UTC datetime string.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(UTC).isoformat()

    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    cur = conn.cursor()

    # Parameterized inserts — no string formatting
    for msg, count in errors.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (timestamp, msg, count),
        )

    for endpoint, times in api_stats.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (timestamp, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    errors: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Write a self-contained HTML report to *output_path* covering:
      - Error summary (message + occurrence count)
      - API latency table (endpoint + average latency)
      - Active session count
    """
    rows = []
    for msg, count in sorted(errors.items(), key=lambda x: -x[1]):
        rows.append(f"<li><b>{_html_escape(msg)}</b>: {count} occurrences</li>")

    error_section = (
        "<h1>Error Summary</h1>\n<ul>\n" + "\n".join(rows) + "\n</ul>\n"
        if rows else "<h1>Error Summary</h1><p>No errors recorded.</p>\n"
    )

    api_rows = []
    for endpoint, times in sorted(api_stats.items()):
        avg = round(sum(times) / len(times), 1)
        api_rows.append(
            f"<tr><td>{_html_escape(endpoint)}</td><td>{avg}</td></tr>"
        )

    api_section = (
        "<h2>API Latency</h2>\n<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        + "\n".join(api_rows)
        + "\n</table>\n"
        if api_rows else "<h2>API Latency</h2><p>No API calls recorded.</p>\n"
    )

    html = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        + error_section
        + api_section
        + "<h2>Active Sessions</h2>\n"
        f"<p>{active_sessions} user(s) currently active</p>\n"
        "</body>\n</html>"
    )

    with open(output_path, "w") as f:
        f.write(html)


def _html_escape(s: str) -> str:
    """Basic HTML escaping for user-controlled strings."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ----------------------------------------------------------------------------- #
# Pipeline entry point
# ----------------------------------------------------------------------------- #

def run_pipeline() -> None:
    """
    Full ETL pipeline: read logs, transform to metrics, persist to DB and HTML.
    """
    db_path = os.environ.get("DB_PATH", "metrics.db")
    log_path = os.environ.get("LOG_FILE", "server.log")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "admin")
    report_path = os.environ.get("REPORT_PATH", "report.html")

    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    entries = extract_log_entries(log_path)
    result = transform_entries(entries)

    load_metrics(db_path, result["errors"], result["api_stats"])

    generate_html_report(
        result["errors"],
        result["api_stats"],
        len(result["active_sessions"]),
        report_path,
    )

    print(f"Job finished at {datetime.datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    log_file = os.environ.get("LOG_FILE", "server.log")
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
