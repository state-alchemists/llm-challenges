"""
Server log processing pipeline.

Extracts log entries, transforms them into metrics, loads results into SQLite
and generates an HTML report.

Usage:
    DB_PATH=metrics.db LOG_FILE=server.log python pipeline_refactored.py
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")

REPORT_PATH: str = os.environ.get("REPORT_PATH", "report.html")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class EntryType(Enum):
    ERROR = "ERR"
    WARNING = "WARN"
    USER_ACTION = "USR"
    API_CALL = "API"


@dataclass
class LogEntry:
    """Represents a parsed log line."""
    timestamp: str
    level: str
    entry_type: EntryType
    # Optional fields based on entry type
    message: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Regex patterns (compiled once)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"ERROR (?P<message>.+)$"
)

_RE_WARNING = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"WARN (?P<message>.+)$"
)

_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO User (?P<user_id>\S+) (?P<action>.+)$"
)

_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO API (?P<endpoint>\S+) took (?P<latency>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> Optional[LogEntry]:
    """
    Parse a single log line into a LogEntry.

    Returns None if the line format is not recognised.
    """
    line = line.strip()
    if not line:
        return None

    # ERROR lines
    m = _RE_ERROR.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level="ERROR",
            entry_type=EntryType.ERROR,
            message=m.group("message"),
        )

    # WARNING lines
    m = _RE_WARNING.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level="WARN",
            entry_type=EntryType.WARNING,
            message=m.group("message"),
        )

    # User action lines (login / logout)
    m = _RE_USER.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level="INFO",
            entry_type=EntryType.USER_ACTION,
            user_id=m.group("user_id"),
            action=m.group("action"),
        )

    # API latency lines
    m = _RE_API.match(line)
    if m:
        return LogEntry(
            timestamp=m.group("timestamp"),
            level="INFO",
            entry_type=EntryType.API_CALL,
            endpoint=m.group("endpoint"),
            latency_ms=int(m.group("latency")),
        )

    return None


def extract_log_entries(log_file: str) -> List[LogEntry]:
    """
    Read *log_file* and return all parsed LogEntry objects.

    Silently skips unrecognised lines.
    """
    entries: List[LogEntry] = []

    if not os.path.exists(log_file):
        print(f"Warning: {log_file} not found — no logs to process.")
        return entries

    with open(log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform_errors(entries: List[LogEntry]) -> Dict[str, int]:
    """
    Aggregate ERROR entries by their message text.

    Returns a dict mapping error message -> occurrence count.
    """
    counts: Dict[str, int] = {}
    for entry in entries:
        if entry.entry_type == EntryType.ERROR and entry.message is not None:
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def transform_api_latency(entries: List[LogEntry]) -> Dict[str, List[int]]:
    """
    Group API call latencies by endpoint.

    Returns a dict mapping endpoint -> list of latency values (ms).
    """
    by_endpoint: Dict[str, List[int]] = {}
    for entry in entries:
        if entry.entry_type == EntryType.API_CALL:
            assert entry.endpoint is not None, "API entry must have an endpoint"
            assert entry.latency_ms is not None, "API entry must have latency_ms"
            by_endpoint.setdefault(entry.endpoint, []).append(entry.latency_ms)
    return by_endpoint


def transform_active_sessions(entries: List[LogEntry]) -> int:
    """
    Count users with an open session at the end of the log.

    A session is opened by a "logged in" action and closed by "logged out".
    Users who logged in but never logged out are considered still active.
    """
    active: Dict[str, str] = {}  # user_id -> login timestamp

    for entry in entries:
        if entry.entry_type == EntryType.USER_ACTION:
            uid = entry.user_id
            assert uid is not None, "USER_ACTION entry must have a user_id"
            action = entry.action or ""

            if "logged in" in action:
                active[uid] = entry.timestamp
            elif "logged out" in action and uid in active:
                del active[uid]

    return len(active)


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the required tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_metrics(
    db_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    credentials: Dict[str, str],
) -> None:
    """
    Write error counts and API latency aggregates into the SQLite database.

    Credentials are acknowledged but SQLite (used here) does not use network
    authentication — they are accepted for API compatibility with callers that
    also target PostgreSQL.
    """
    print(
        f"Connecting to {credentials['host']}:{credentials['port']} "
        f"as {credentials['user']}..."
    )

    conn = sqlite3.connect(db_path)
    try:
        ensure_tables(conn)

        now = datetime.datetime.now().isoformat()

        # Insert error aggregates — parameterised query prevents injection
        for msg, count in error_counts.items():
            conn.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        # Insert API latency aggregates
        for endpoint, latencies in api_metrics.items():
            avg_ms = sum(latencies) / len(latencies)
            conn.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Render the summary data as an HTML report written to *output_path*.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        # Escape HTML special characters to prevent XSS within the report
        safe_msg = (
            err_msg.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
        )
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, latencies in api_metrics.items():
        avg = sum(latencies) / len(latencies)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Report written to {output_path}")


# ---------------------------------------------------------------------------
# Main pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline:

    1. Extract — read and parse the log file.
    2. Transform — build error counts, API latency aggregates, session count.
    3. Load — write metrics to SQLite and emit the HTML report.
    """
    credentials = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "pass": DB_PASS,
    }

    # ── Extract ────────────────────────────────────────────────────────────
    entries = extract_log_entries(LOG_FILE)
    print(f"Extracted {len(entries)} log entries from {LOG_FILE}.")

    # ── Transform ───────────────────────────────────────────────────────────
    error_counts = transform_errors(entries)
    api_metrics = transform_api_latency(entries)
    active_sessions = transform_active_sessions(entries)

    # ── Load ───────────────────────────────────────────────────────────────
    load_metrics(DB_PATH, error_counts, api_metrics, credentials)
    generate_html_report(error_counts, api_metrics, active_sessions, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now().isoformat()}")


# ---------------------------------------------------------------------------
# Bootstrap — create a sample log when the file is absent (dev convenience)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as fh:
            fh.write("\n".join(sample_lines) + "\n")
        print(f"Created sample log: {LOG_FILE}")

    run_pipeline()
