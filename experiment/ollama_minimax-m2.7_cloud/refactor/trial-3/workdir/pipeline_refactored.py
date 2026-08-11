#!/usr/bin/env python3
"""
Log processing pipeline that extracts server logs, transforms the data,
and loads it into a SQLite database with an HTML report output.

Configuration is read from environment variables:
    DB_PATH       - Path to SQLite database (default: metrics.db)
    LOG_FILE      - Path to server log file (default: server.log)
    DB_HOST       - Database host (default: localhost)
    DB_PORT       - Database port (default: 5432)
    DB_USER       - Database username (default: admin)
    DB_PASSWORD   - Database password (default: password123)
"""

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# Configuration from environment variables
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password123")


class LogEntry(TypedDict):
    """Structured log entry."""
    dt: str
    t: str
    m: str
    u: str | None
    a: str | int | None


class APICall(TypedDict):
    """API call record with latency."""
    d: str
    endpoint: str
    ms: int


# Regex patterns for log parsing
_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN)"
)
_RE_USER_ACTION = re.compile(
    r"User (?P<uid>\S+) (?P<action>logged in|logged out)"
)
_RE_API_CALL = re.compile(
    r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms"
)


def _load_config() -> dict:
    """
    Load and return configuration from environment variables.

    Returns:
        Dictionary with database and file path configuration.
    """
    return {
        "db_path": DB_PATH,
        "log_file": LOG_FILE,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_user": DB_USER,
    }


def _extract_log_entries(log_path: str) -> list[LogEntry]:
    """
    Read and parse log file, extracting structured entries.

    Args:
        log_path: Path to the server log file.

    Returns:
        List of parsed log entries with timestamp, type, and metadata.
    """
    entries: list[LogEntry] = []

    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            base_match = _RE_LOG_LINE.match(line)
            if not base_match:
                continue

            timestamp = base_match.group("timestamp")
            level = base_match.group("level")

            if level == "ERROR":
                message = line[base_match.end() :].strip()
                entries.append(LogEntry(dt=timestamp, t="ERR", m=message, u=None, a=None))

            elif level == "WARN":
                message = line[base_match.end() :].strip()
                entries.append(LogEntry(dt=timestamp, t="WARN", m=message, u=None, a=None))

            elif level == "INFO":
                user_match = _RE_USER_ACTION.search(line)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action")
                    entries.append(LogEntry(dt=timestamp, t="USR", m="", u=uid, a=action))

                api_match = _RE_API_CALL.search(line)
                if api_match:
                    entries.append(LogEntry(
                        dt=timestamp,
                        t="API",
                        m="",
                        u=api_match.group("endpoint"),
                        a=int(api_match.group("ms")),
                    ))

    return entries


def _extract_api_calls(log_path: str) -> list[APICall]:
    """
    Extract API call records with endpoint and latency from log file.

    Args:
        log_path: Path to the server log file.

    Returns:
        List of API call records.
    """
    calls: list[APICall] = []

    if not os.path.exists(log_path):
        return calls

    with open(log_path, "r") as f:
        for line in f:
            base_match = _RE_LOG_LINE.match(line)
            if not base_match or base_match.group("level") != "INFO":
                continue

            api_match = _RE_API_CALL.search(line)
            if api_match:
                calls.append(APICall(
                    d=base_match.group("timestamp"),
                    endpoint=api_match.group("endpoint"),
                    ms=int(api_match.group("ms")),
                ))

    return calls


def _track_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """
    Track active user sessions from log entries.

    Args:
        entries: List of parsed log entries.

    Returns:
        Dictionary mapping user IDs to their login timestamps.
    """
    sessions: dict[str, str] = {}

    for entry in entries:
        if entry["t"] != "USR" or entry["u"] is None or entry["a"] is None:
            continue

        uid = entry["u"]
        action = str(entry["a"])

        if "logged in" in action:
            sessions[uid] = entry["dt"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]

    return sessions


def _count_errors(entries: list[LogEntry]) -> dict[str, int]:
    """
    Count occurrences of each error message.

    Args:
        entries: List of parsed log entries.

    Returns:
        Dictionary mapping error messages to occurrence counts.
    """
    counts: dict[str, int] = {}

    for entry in entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            counts[msg] = counts.get(msg, 0) + 1

    return counts


def _compute_api_latency(api_calls: list[APICall]) -> dict[str, float]:
    """
    Compute average latency per endpoint from API call records.

    Args:
        api_calls: List of API call records.

    Returns:
        Dictionary mapping endpoints to their average latency in ms.
    """
    by_endpoint: dict[str, list[int]] = {}

    for call in api_calls:
        ep = call["endpoint"]
        by_endpoint.setdefault(ep, []).append(call["ms"])

    return {ep: sum(times) / len(times) for ep, times in by_endpoint.items()}


def _init_database(db_path: str) -> sqlite3.Connection:
    """
    Initialize SQLite database with required tables.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Open database connection.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def _load_errors(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Insert error summary records into the database using parameterized queries.

    Args:
        conn: Database connection.
        error_counts: Dictionary of error messages to counts.
    """
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.executemany(
        "INSERT INTO errors VALUES (?, ?, ?)",
        [(now, msg, count) for msg, count in error_counts.items()],
    )
    conn.commit()


def _load_api_metrics(conn: sqlite3.Connection, latency: dict[str, float]) -> None:
    """
    Insert API latency records into the database using parameterized queries.

    Args:
        conn: Database connection.
        latency: Dictionary of endpoints to average latencies.
    """
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.executemany(
        "INSERT INTO api_metrics VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in latency.items()],
    )
    conn.commit()


def _generate_report(
    error_counts: dict[str, int],
    latency: dict[str, float],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Generate HTML report with error summary, API latency, and session count.

    Args:
        error_counts: Dictionary of error messages to counts.
        latency: Dictionary of endpoints to average latencies.
        active_sessions: Number of currently active sessions.
        output_path: Path to write the HTML report.
    """
    lines: list[str] = [
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

    for ep, avg in latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract, transform, load, and report.
    """
    config = _load_config()
    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    # Extract
    entries = _extract_log_entries(config["log_file"])
    api_calls = _extract_api_calls(config["log_file"])

    # Transform
    error_counts = _count_errors(entries)
    sessions = _track_sessions(entries)
    latency = _compute_api_latency(api_calls)
    active_session_count = len(sessions)

    # Load
    conn = _init_database(config["db_path"])
    _load_errors(conn, error_counts)
    _load_api_metrics(conn, latency)
    conn.close()

    # Report
    _generate_report(error_counts, latency, active_session_count, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create sample log file if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
