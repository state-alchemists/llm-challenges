"""
Pipeline: Parse server logs, store metrics in DB, and generate an HTML report.

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
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class LogEntry(NamedTuple):
    """A parsed log record."""
    timestamp: str
    level: str          # "ERROR" | "WARN" | "INFO"
    message: str = ""
    user_id: str = ""   # populated for INFO User lines
    action: str = ""    # populated for INFO User lines
    endpoint: str = ""  # populated for INFO API lines
    latency_ms: int = 0  # populated for INFO API lines


class ProcessedData(NamedTuple):
    """Structured data extracted from logs."""
    errors: dict[str, int]          # message -> count
    api_latency: dict[str, list[int]]  # endpoint -> list of latencies (ms)
    active_sessions: set[str]        # user IDs currently logged in


# ---------------------------------------------------------------------------
# Extract – read and parse log file with regex
# ---------------------------------------------------------------------------

# Format: "2024-01-01 12:00:00 LEVEL <rest>"
_LOG_BASE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.+)$"
)

# INFO User <id> <action>
_LOG_USER_PATTERN = re.compile(
    r"^User (?P<user_id>\d+) (?P<action>.+)$"
)

# INFO API <endpoint> took <ms>ms
_LOG_API_PATTERN = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


def parse_log_line(line: str) -> LogEntry | None:
    """
    Parse a single log line into a LogEntry.

    Returns None for unrecognised lines.
    """
    m = _LOG_BASE_PATTERN.match(line.strip())
    if not m:
        return None

    timestamp = m.group("timestamp")
    level = m.group("level")
    rest = m.group("rest")

    entry = LogEntry(timestamp=timestamp, level=level)

    if level == "ERROR" or level == "WARN":
        return entry._replace(message=rest)

    if level == "INFO":
        user_m = _LOG_USER_PATTERN.match(rest)
        if user_m:
            return entry._replace(
                user_id=user_m.group("user_id"),
                action=user_m.group("action"),
            )

        api_m = _LOG_API_PATTERN.match(rest)
        if api_m:
            return entry._replace(
                endpoint=api_m.group("endpoint"),
                latency_ms=int(api_m.group("ms")),
            )

    return None


def extract_logs(path: str) -> list[LogEntry]:
    """
    Read *path* and return all parsed LogEntry objects.

    Silently skips unrecognised lines.
    """
    if not os.path.exists(path):
        return []

    entries: list[LogEntry] = []
    with open(path, "r") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform – convert raw entries into report-ready data structures
# ---------------------------------------------------------------------------

def transform(entries: list[LogEntry]) -> ProcessedData:
    """
    Aggregate *entries* into error counts, API latency buckets, and active sessions.
    """
    errors: dict[str, int] = {}
    api_latency: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}  # user_id -> timestamp

    for e in entries:
        if e.level == "ERROR":
            errors[e.message] = errors.get(e.message, 0) + 1

        elif e.level == "INFO" and e.user_id:
            if "logged in" in e.action:
                sessions[e.user_id] = e.timestamp
            elif "logged out" in e.action and e.user_id in sessions:
                del sessions[e.user_id]

        elif e.level == "INFO" and e.endpoint:
            api_latency.setdefault(e.endpoint, []).append(e.latency_ms)

    return ProcessedData(
        errors=errors,
        api_latency=api_latency,
        active_sessions=set(sessions),
    )


# ---------------------------------------------------------------------------
# Load – write to DB and emit HTML report
# ---------------------------------------------------------------------------

def _connect_db(path: str) -> sqlite3.Connection:
    """Open a connection to the SQLite DB at *path*."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def _build_html_report(data: ProcessedData) -> str:
    """Render ProcessedData as an HTML string."""
    now = datetime.datetime.now().isoformat()

    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"  <title>System Report — {now}</title>",
        "</head>",
        "<body>",
        "  <h1>Error Summary</h1>",
        "  <ul>",
    ]

    if data.errors:
        for msg, count in data.errors.items():
            lines.append(f"    <li><b>{msg}</b>: {count} occurrences</li>")
    else:
        lines.append("    <li>No errors recorded.</li>")

    lines.extend([
        "  </ul>",
        "",
        "  <h2>API Latency</h2>",
        "  <table border='1'>",
        "    <tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if data.api_latency:
        for endpoint, latencies in data.api_latency.items():
            avg = sum(latencies) / len(latencies)
            lines.append(
                f"    <tr><td>{endpoint}</td>"
                f"<td>{round(avg, 1)}</td></tr>"
            )
    else:
        lines.append("    <tr><td colspan='2'>No API calls recorded.</td></tr>")

    lines.extend([
        "  </table>",
        "",
        "  <h2>Active Sessions</h2>",
        f"  <p>{len(data.active_sessions)} user(s) currently active</p>",
        "",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def load(data: ProcessedData, db_path: str, report_path: str) -> None:
    """
    Persist *data* to the SQLite DB at *db_path* and write the HTML report
    to *report_path*.
    """
    conn = _connect_db(db_path)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    # Insert error summary – parameterised
    for msg, count in data.errors.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    # Insert API latency averages – parameterised
    for endpoint, latencies in data.api_latency.items():
        avg = sum(latencies) / len(latencies)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()

    # Write HTML report
    html = _build_html_report(data)
    with open(report_path, "w") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Full ETL pipeline: extract → transform → load."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    entries = extract_logs(LOG_FILE)
    print(f"Parsed {len(entries)} log entries from {LOG_FILE}.")

    data = transform(entries)
    print(
        f"Transform: {len(data.errors)} error types, "
        f"{len(data.api_latency)} API endpoints, "
        f"{len(data.active_sessions)} active sessions."
    )

    load(data, DB_PATH, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap – create a minimal sample log when none exists
# ---------------------------------------------------------------------------

def _bootstrap_log(path: str) -> None:
    """Write a sample log file so the script works out-of-the-box."""
    sample = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    with open(path, "w") as fh:
        fh.write(sample)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        _bootstrap_log(LOG_FILE)

    run_pipeline()
