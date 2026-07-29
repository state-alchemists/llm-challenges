"""
Pipeline module for extracting, transforming, and loading server log metrics.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Set

# Configuration loaded from environment variables with defaults
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


@dataclass
class LogMetrics:
    """Dataclass representing extracted and transformed log metrics."""
    errors: Dict[str, int]
    api_calls: Dict[str, List[int]]
    active_sessions: Set[str]


def extract_logs(log_file_path: str) -> List[str]:
    """Reads all lines from the log file.

    Args:
        log_file_path: Path to the log file.

    Returns:
        A list of raw log lines.
    """
    if not os.path.exists(log_file_path):
        return []
    with open(log_file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def _parse_user_action(msg: str, sessions: Set[str]) -> None:
    """Helper to parse user action and update sessions set.

    Args:
        msg: Message content from the log line.
        sessions: Set of active session user IDs to update.
    """
    if not msg.startswith("User"):
        return
    match = re.match(r'^User (\S+) (.+)$', msg)
    if not match:
        return
    uid, action = match.groups()
    if "logged in" in action:
        sessions.add(uid)
    elif "logged out" in action:
        sessions.discard(uid)


def _parse_api_call(msg: str, api_calls: Dict[str, List[int]]) -> None:
    """Helper to parse API call and update api_calls dictionary.

    Args:
        msg: Message content from the log line.
        api_calls: Dictionary mapping endpoints to lists of durations.
    """
    if not msg.startswith("API"):
        return
    match = re.match(r'^API (\S+)(?: took (\d+)ms)?', msg)
    if not match:
        return
    endpoint, ms_str = match.groups()
    ms = int(ms_str) if ms_str is not None else 0
    api_calls.setdefault(endpoint, []).append(ms)


def transform_logs(lines: List[str]) -> LogMetrics:
    """Parses raw log lines into structured metrics using regular expressions.

    Args:
        lines: A list of raw log lines.

    Returns:
        A LogMetrics object containing summarized errors, api calls, and sessions.
    """
    errors: Dict[str, int] = {}
    api_calls: Dict[str, List[int]] = {}
    sessions: Set[str] = set()

    log_pattern = re.compile(
        r'^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>[A-Z]+) (?P<msg>.*)$'
    )

    for line in lines:
        match = log_pattern.match(line.strip())
        if not match:
            continue

        lvl = match.group("lvl")
        msg = match.group("msg")

        if lvl == "ERROR":
            errors[msg] = errors.get(msg, 0) + 1
        elif lvl == "INFO":
            _parse_user_action(msg, sessions)
            _parse_api_call(msg, api_calls)

    return LogMetrics(errors=errors, api_calls=api_calls, active_sessions=sessions)


def load_to_database(
    db_path: str,
    errors: Dict[str, int],
    api_calls: Dict[str, List[int]]
) -> None:
    """Saves log metrics to SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        errors: Error message counts.
        api_calls: API endpoints execution times list.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        current_time = str(datetime.datetime.now())

        for msg, count in errors.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (current_time, msg, count)
            )

        for ep, times in api_calls.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (current_time, ep, avg)
                )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    report_path: str,
    errors: Dict[str, int],
    api_calls: Dict[str, List[int]],
    active_sessions_count: int
) -> None:
    """Generates an HTML summary report from the metrics.

    Args:
        report_path: File path for the generated report.
        errors: Error message counts.
        api_calls: API endpoints execution times list.
        active_sessions_count: Count of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_calls.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main pipeline orchestrator."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    log_lines = extract_logs(LOG_FILE)

    # Transform
    metrics = transform_logs(log_lines)

    # Load
    load_to_database(DB_PATH, metrics.errors, metrics.api_calls)
    generate_html_report(
        "report.html",
        metrics.errors,
        metrics.api_calls,
        len(metrics.active_sessions)
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as file_handle:
            file_handle.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            file_handle.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            file_handle.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            file_handle.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            file_handle.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            file_handle.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
