"""Log parsing and system reporting pipeline.

This module extracts server logs, transforms them to compute error frequencies,
API metrics, and active session counts, and then loads/outputs the structured
metrics into a database and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple

# Configuration using environment variables with defaults
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex pattern compilers for robust log parsing
LOG_PATTERN = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<lvl>\w+)\s+(?P<msg>.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")
API_PATTERN = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?")


def extract_log_lines(filepath: str) -> List[str]:
    """Extract raw log lines from the given log file.

    Args:
        filepath: Path to the log file.

    Returns:
        A list of raw log lines.
    """
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _process_user_session(dt: str, msg: str, sessions: Dict[str, str]) -> None:
    """Process a user session log message.

    Args:
        dt: Datetime string of the log entry.
        msg: Log message body.
        sessions: Dictionary tracking active user sessions.
    """
    match = USER_PATTERN.match(msg)
    if not match:
        return

    uid = match.group("uid")
    action = match.group("action")

    if "logged in" in action:
        sessions[uid] = dt
    elif "logged out" in action:
        sessions.pop(uid, None)


def _process_api_call(msg: str, api_calls: Dict[str, List[int]]) -> None:
    """Process an API call log message.

    Args:
        msg: Log message body.
        api_calls: Dictionary mapping endpoints to a list of latencies (ms).
    """
    match = API_PATTERN.match(msg)
    if not match:
        return

    endpoint = match.group("endpoint")
    dur_str = match.group("dur")
    dur = int(dur_str) if dur_str is not None else 0
    api_calls.setdefault(endpoint, []).append(dur)


def process_log_line(
    line: str,
    error_counts: Dict[str, int],
    api_calls: Dict[str, List[int]],
    sessions: Dict[str, str],
) -> None:
    """Parse and process a single log line, updating the metrics collections.

    Args:
        line: Raw log line to process.
        error_counts: Dictionary mapping error messages to occurrence counts.
        api_calls: Dictionary mapping endpoints to a list of latencies (ms).
        sessions: Dictionary tracking active user sessions.
    """
    match = LOG_PATTERN.match(line)
    if not match:
        return

    dt = match.group("dt")
    lvl = match.group("lvl")
    msg = match.group("msg")

    if lvl == "ERROR":
        error_counts[msg] = error_counts.get(msg, 0) + 1
    elif lvl == "INFO" and "User" in msg:
        _process_user_session(dt, msg, sessions)
    elif lvl == "INFO" and "API" in msg:
        _process_api_call(msg, api_calls)


def transform_log_data(
    lines: List[str]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Transform raw log lines into structured metrics.

    Processes errors to calculate frequencies, parses API endpoints to compile
    latencies, and tracks user logins/logouts to determine active sessions.

    Args:
        lines: A list of raw log lines.

    Returns:
        A tuple containing:
          - A dictionary mapping error messages to their occurrence count.
          - A dictionary mapping API endpoints to a list of latencies (ms).
          - The count of currently active user sessions.
    """
    error_counts: Dict[str, int] = {}
    api_calls: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for line in lines:
        process_log_line(line, error_counts, api_calls, sessions)

    return error_counts, api_calls, len(sessions)


def load_metrics_to_db(
    db_path: str,
    error_counts: Dict[str, int],
    api_calls: Dict[str, List[int]]
) -> None:
    """Load calculated metrics into the SQLite database securely.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Dictionary mapping error messages to counts.
        api_calls: Dictionary mapping endpoints to a list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            # Use parameterized query for protection against SQL injection
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count)
            )

        for ep, times in api_calls.items():
            if times:
                avg = sum(times) / len(times)
                # Use parameterized query for protection against SQL injection
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg)
                )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_calls: Dict[str, List[int]],
    active_sessions_count: int
) -> None:
    """Generate the HTML report containing metrics summary.

    Args:
        report_path: Path where the HTML report will be saved.
        error_counts: Dictionary of error messages to counts.
        api_calls: Dictionary of API endpoints to latencies.
        active_sessions_count: Count of currently active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_calls.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution function coordinating the ETL pipeline."""
    # Ensure raw log exists for testing if not found
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    raw_lines = extract_log_lines(LOG_FILE)

    # Transform
    error_counts, api_calls, active_sessions = transform_log_data(raw_lines)

    # Load / Output
    load_metrics_to_db(DB_PATH, error_counts, api_calls)
    generate_report("report.html", error_counts, api_calls, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
