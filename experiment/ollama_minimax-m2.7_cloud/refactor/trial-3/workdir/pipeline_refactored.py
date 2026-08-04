"""
Log processing pipeline that extracts metrics from server logs,
transforms them, and loads results into SQLite + HTML report.

Usage:
    python pipeline_refactored.py

Configuration via environment variables:
    DB_PATH       - Path to SQLite database (default: metrics.db)
    LOG_FILE      - Path to server log file (default: server.log)
    DB_HOST       - Database host (default: localhost)
    DB_PORT       - Database port (default: 5432)
    DB_USER       - Database user (default: admin)
    DB_PASS       - Database password (default: password123)
"""

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Typed data structures
# ---------------------------------------------------------------------------

LogEntry = TypedDict("LogEntry", {"dt": str, "t": str, "m": str})
UserEntry = TypedDict("UserEntry", {"dt": str, "t": str, "u": str, "a": str})
APIEntry = TypedDict("APIEntry", {"dt": str, "endpoint": str, "ms": int})
ParsedLog = tuple[list[LogEntry], list[UserEntry], list[APIEntry]]


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Regex patterns for structured log parsing
_RE_LOG_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)")

_RE_ERROR = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$")
_RE_WARN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.+)$")
_RE_USER = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.+)$"
)
_RE_API = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"
)


def extract_from_log(log_path: str) -> ParsedLog:
    """
    Parse a server log file and extract structured records.

    Args:
        log_path: Path to the server log file.

    Returns:
        A 3-tuple of:
        - error_warn_entries: ERROR and WARN log entries
        - user_entries: INFO User activity entries (login/logout)
        - api_entries: INFO API latency entries
    """
    errors: list[LogEntry] = []
    warnings: list[LogEntry] = []
    users: list[UserEntry] = []
    api_calls: list[APIEntry] = []

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return [], [], []

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")

            # ERROR lines
            m = _RE_ERROR.match(line)
            if m:
                errors.append({"dt": m.group(1), "t": "ERR", "m": m.group(2)})
                continue

            # WARN lines
            m = _RE_WARN.match(line)
            if m:
                warnings.append({"dt": m.group(1), "t": "WARN", "m": m.group(2)})
                continue

            # INFO User <id> <action>
            m = _RE_USER.match(line)
            if m:
                users.append({
                    "dt": m.group(1),
                    "t": "USR",
                    "u": m.group(2),
                    "a": m.group(3),
                })
                continue

            # INFO API <endpoint> took <ms>ms
            m = _RE_API.match(line)
            if m:
                api_calls.append({
                    "dt": m.group(1),
                    "endpoint": m.group(2),
                    "ms": int(m.group(3)),
                })
                continue

    return errors + warnings, users, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

ErrorSummary = dict[str, int]
EndpointLatency = dict[str, list[int]]
ActiveSessions = dict[str, str]  # uid -> last seen datetime


def transform_to_error_summary(entries: list[LogEntry]) -> ErrorSummary:
    """
    Aggregate log entries by message to produce error/warn counts.

    Args:
        entries: Combined ERROR and WARN log entries.

    Returns:
        Dictionary mapping message text to occurrence count.
    """
    summary: ErrorSummary = {}
    for entry in entries:
        msg = entry["m"]
        summary[msg] = summary.get(msg, 0) + 1
    return summary


def transform_to_endpoint_latency(api_calls: list[APIEntry]) -> EndpointLatency:
    """
    Group API calls by endpoint and collect latency values.

    Args:
        api_calls: List of API call records.

    Returns:
        Dictionary mapping endpoint name to list of latency values (ms).
    """
    latency: EndpointLatency = {}
    for call in api_calls:
        latency.setdefault(call["endpoint"], []).append(call["ms"])
    return latency


def transform_to_active_sessions(user_entries: list[UserEntry]) -> ActiveSessions:
    """
    Track active sessions by parsing login/logout events.

    A user is considered active from their most recent login until their
    logout event. Users without a matching logout remain active.

    Args:
        user_entries: List of User activity records.

    Returns:
        Dictionary mapping user ID to session start datetime.
    """
    sessions: ActiveSessions = {}
    for entry in user_entries:
        uid = entry["u"]
        action = entry["a"]
        if "logged in" in action:
            sessions[uid] = entry["dt"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_summary: ErrorSummary,
    endpoint_latency: EndpointLatency,
) -> None:
    """
    Write aggregated metrics into the SQLite database.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Error/warn counts by message.
        endpoint_latency: Per-endpoint latency lists.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now()
    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in endpoint_latency.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    output_path: str,
    error_summary: ErrorSummary,
    endpoint_latency: EndpointLatency,
    active_sessions: ActiveSessions,
) -> None:
    """
    Render the aggregated metrics as an HTML report.

    Args:
        output_path: Destination file path for the HTML report.
        error_summary: Error/warn counts by message.
        endpoint_latency: Per-endpoint latency lists.
        active_sessions: Active user sessions (uid -> login time).
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # Error Summary
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in error_summary.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    # API Latency
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in endpoint_latency.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    # Active Sessions
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline:
    1. Extract - parse log file
    2. Transform - aggregate into error/latency/session summaries
    3. Load - write to database and generate HTML report
    """
    # Extract
    log_entries, user_entries, api_calls = extract_from_log(LOG_FILE)

    # Transform
    error_summary = transform_to_error_summary(log_entries)
    endpoint_latency = transform_to_endpoint_latency(api_calls)
    active_sessions = transform_to_active_sessions(user_entries)

    # Load
    load_to_database(DB_PATH, error_summary, endpoint_latency)
    generate_html_report("report.html", error_summary, endpoint_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bootstrap a sample log when the file is absent so the script runs
    # end-to-end without manual setup.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
