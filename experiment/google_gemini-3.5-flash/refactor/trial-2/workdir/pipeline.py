"""
Log Processing Pipeline

This script extracts server log entries, parses and transforms them to calculate key metrics,
and then loads the results into a database and generates an HTML summary report.

Environment Variables:
    DB_PATH: Path to the SQLite metrics database (default: 'metrics.db')
    LOG_FILE: Path to the server log file (default: 'server.log')
    DB_HOST: Host name for DB connection logging (default: 'localhost')
    DB_PORT: Port number for DB connection logging (default: '5432')
    DB_USER: Username for DB connection logging (default: 'admin')
    DB_PASS: Password for DB connection logging (default: 'password123')
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Set

# --- Configuration (Loaded from Environment Variables) ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Regular Expressions for Log Parsing ---
# General format: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
LOG_PATTERN = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>ERROR|INFO|WARN) (?P<msg>.*)$"
)
USER_PATTERN = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")
API_PATTERN = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?")


@dataclass
class LogMetrics:
    """
    Data structure containing the aggregated metrics parsed from server logs.
    """
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_users: Set[str] = field(default_factory=set)


# --- Extract ---
def extract_log_lines(file_path: str) -> List[str]:
    """
    Reads all raw lines from the specified log file.

    Args:
        file_path: Path to the log file.

    Returns:
        A list of raw log lines. If the file does not exist, returns an empty list.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


# --- Transform ---
def _parse_user_action(msg: str, active_users: Set[str]) -> None:
    """
    Parses user actions from INFO message and updates the active_users set.
    """
    user_match = USER_PATTERN.match(msg)
    if not user_match:
        return
    uid = user_match.group("uid")
    action = user_match.group("action")
    if "logged in" in action:
        active_users.add(uid)
    elif "logged out" in action:
        active_users.discard(uid)


def _parse_api_latency(msg: str, api_latencies: Dict[str, List[int]]) -> None:
    """
    Parses API latency from INFO message and updates the api_latencies map.
    """
    api_match = API_PATTERN.match(msg)
    if not api_match:
        return
    endpoint = api_match.group("endpoint")
    ms_str = api_match.group("ms")
    ms = int(ms_str) if ms_str else 0
    api_latencies.setdefault(endpoint, []).append(ms)


def transform_logs(lines: List[str]) -> LogMetrics:
    """
    Parses raw log lines and aggregates metrics.

    Processes:
    - ERROR logs: counts occurrences of each error message.
    - INFO logs (User): tracks active user sessions.
    - INFO logs (API): tracks response times (latency) for each endpoint.

    Args:
        lines: A list of raw log lines.

    Returns:
        A LogMetrics dataclass containing the computed aggregates.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_users: Set[str] = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            continue

        lvl = match.group("lvl")
        msg = match.group("msg")

        if lvl == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif lvl == "INFO":
            _parse_user_action(msg, active_users)
            _parse_api_latency(msg, api_latencies)

    return LogMetrics(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_users=active_users,
    )


# --- Load ---
def load_to_database(metrics: LogMetrics, db_path: str) -> None:
    """
    Stores error frequencies and average API metrics into the SQLite database.

    Creates tables if they do not exist, and inserts records using parameterized
    queries to prevent SQL injection.

    Args:
        metrics: The LogMetrics dataclass containing aggregated metrics.
        db_path: Path to the SQLite database.
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

        # Record metrics with current run time
        for msg, count in metrics.error_counts.items():
            now_str = str(datetime.datetime.now())
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in metrics.api_latencies.items():
            if times:
                avg = sum(times) / len(times)
                now_str = str(datetime.datetime.now())
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def load_to_html_report(metrics: LogMetrics, report_path: str) -> None:
    """
    Generates a structured HTML report summarizing log statistics.

    Args:
        metrics: The LogMetrics dataclass containing aggregated metrics.
        report_path: Destination path for the HTML report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics.api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(metrics.active_users)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """
    Executes the complete ETL (Extract, Transform, Load) pipeline.
    """
    # Extract
    lines = extract_log_lines(LOG_FILE)

    # Transform
    metrics = transform_logs(lines)

    # Load
    load_to_database(metrics, DB_PATH)
    load_to_html_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Ensure raw data source exists with initial data if missing, as in original script.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
