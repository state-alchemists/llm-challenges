"""Log analysis and reporting pipeline.

This script processes server logs, extracts key system metrics (errors,
API latency, and active sessions), saves the aggregated data to a database,
and generates an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration using environment variables with sensible defaults
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular expressions for log parsing
LOG_LINE_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
USER_PATTERN: re.Pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN: re.Pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def extract_log_data(file_path: str) -> List[Dict[str, Any]]:
    """Extract and parse log lines from a log file.

    Args:
        file_path: Path to the log file.

    Returns:
        A list of parsed log events as dictionaries.
    """
    events: List[Dict[str, Any]] = []
    if not os.path.exists(file_path):
        return events

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_stripped: str = line.strip()
            if not line_stripped:
                continue
            match: re.Match | None = LOG_LINE_PATTERN.match(line_stripped)
            if not match:
                continue

            date_part, time_part, level, message = match.groups()
            dt: str = f"{date_part} {time_part}"

            if level == "ERROR":
                events.append({
                    "dt": dt,
                    "type": "ERR",
                    "message": message.strip()
                })
            elif level == "INFO":
                if "User" in message:
                    user_match: re.Match | None = USER_PATTERN.match(message)
                    if user_match:
                        uid, action = user_match.groups()
                        events.append({
                            "dt": dt,
                            "type": "USR",
                            "uid": uid,
                            "action": action.strip()
                        })
                elif "API" in message:
                    api_match: re.Match | None = API_PATTERN.match(message)
                    if api_match:
                        endpoint, ms_str = api_match.groups()
                        ms: int = int(ms_str) if ms_str else 0
                        events.append({
                            "dt": dt,
                            "type": "API",
                            "endpoint": endpoint,
                            "ms": ms
                        })
            elif level == "WARN":
                events.append({
                    "dt": dt,
                    "type": "WARN",
                    "message": message.strip()
                })

    return events


def transform_log_data(
    events: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Transform log events into aggregated metrics.

    Args:
        events: A list of parsed log events.

    Returns:
        A tuple of:
        - Dict mapping error messages to occurrence counts.
        - Dict mapping API endpoints to lists of response latencies (in ms).
        - Total count of active user sessions.
    """
    error_counts: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for ev in events:
        ev_type: str = ev["type"]
        dt: str = ev["dt"]

        if ev_type == "ERR":
            msg: str = ev["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif ev_type == "USR":
            uid: str = ev["uid"]
            action: str = ev["action"]
            if "logged in" in action:
                sessions[uid] = dt
            elif "logged out" in action and uid in sessions:
                sessions.pop(uid)

        elif ev_type == "API":
            endpoint: str = ev["endpoint"]
            ms: int = ev["ms"]
            api_metrics.setdefault(endpoint, []).append(ms)

    return error_counts, api_metrics, len(sessions)


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]]
) -> None:
    """Load aggregated metrics to the SQLite database.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Dictionary of error messages and counts.
        api_metrics: Dictionary of API endpoints and response times.
    """
    conn: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        c: sqlite3.Cursor = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str: str = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            # Use parameterized query to prevent SQL injection!
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count)
            )

        for ep, times in api_metrics.items():
            avg_ms: float = sum(times) / len(times) if times else 0.0
            # Use parameterized query to prevent SQL injection!
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) "
                "VALUES (?, ?, ?)",
                (now_str, ep, avg_ms)
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_sessions_count: int
) -> None:
    """Generate the HTML summary report.

    Args:
        report_path: Destination path for the HTML file.
        error_counts: Dictionary of error messages and counts.
        api_metrics: Dictionary of API endpoints and response times.
        active_sessions_count: Count of currently active sessions.
    """
    out: str = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        avg: float = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrate the ETL pipeline to process log data and generate reports."""
    # Print database connection setup using environment variables
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    events: List[Dict[str, Any]] = extract_log_data(LOG_FILE)

    # Transform
    error_counts, api_metrics, active_sessions_count = transform_log_data(
        events
    )

    # Load: Database
    load_to_database(DB_PATH, error_counts, api_metrics)

    # Load: HTML Report
    generate_report("report.html", error_counts, api_metrics, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_out:
            f_out.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_out.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_out.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_out.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
