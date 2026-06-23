"""
Server Log Parsing and Metrics Generation Pipeline.

This script extracts log data from a server log file, transforms it into
meaningful metrics (such as error frequency, API endpoint latency, and
active user sessions), and loads the structured data into a SQLite database
and generates an HTML report.
"""

from dataclasses import dataclass
import datetime
import os
import re
import sqlite3
from typing import Dict, List

# Configuration via Environment Variables with standard defaults
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")
REPORT_FILE = os.environ.get("REPORT_FILE", "report.html")

# Regular expressions for log line parsing
# Expected format: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
LOG_LINE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<lvl>[A-Z]+)\s+(?P<msg>.*)$"
)

# User action format: User <id> <action>
USER_ACTION_RE = re.compile(r"^User (?P<uid>\S+)\s+(?P<action>.*)$")

# API metric format: API <endpoint>[ took <duration>ms]
API_CALL_RE = re.compile(r"API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?")


@dataclass
class LogMetrics:
    """
    Data container holding aggregated metrics extracted from server logs.

    Attributes:
        errors: Dictionary mapping error messages to their occurrence counts.
        api_metrics: Dictionary mapping API endpoints to lists of latency measurements.
        active_session_count: The number of user sessions active at the end of the log.
    """

    errors: Dict[str, int]
    api_metrics: Dict[str, List[int]]
    active_session_count: int


def extract_log_lines(file_path: str) -> List[str]:
    """
    Extracts raw lines from the log file.

    Args:
        file_path: Path to the server log file.

    Returns:
        A list of raw log lines.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_log_lines(lines: List[str]) -> LogMetrics:
    """
    Parses and aggregates log data using regular expressions.

    Processes errors, user login/logout actions (for active sessions), and
    API performance latencies.

    Args:
        lines: Raw lines from the log file.

    Returns:
        An aggregated LogMetrics instance.
    """
    errors: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for line in lines:
        match = LOG_LINE_RE.match(line.strip())
        if not match:
            continue

        dt = match.group("dt")
        lvl = match.group("lvl")
        msg = match.group("msg")

        if lvl == "ERROR":
            err_msg = msg.strip()
            errors[err_msg] = errors.get(err_msg, 0) + 1

        elif lvl == "INFO":
            # Check for user session actions
            user_match = USER_ACTION_RE.match(msg)
            if user_match:
                uid = user_match.group("uid")
                action = user_match.group("action").strip()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)

            # Check for API endpoint metrics
            api_match = API_CALL_RE.search(msg)
            if api_match:
                endpoint = api_match.group("endpoint")
                dur_str = api_match.group("dur")
                ms = int(dur_str) if dur_str else 0
                api_metrics.setdefault(endpoint, []).append(ms)

    return LogMetrics(
        errors=errors,
        api_metrics=api_metrics,
        active_session_count=len(sessions),
    )


def load_to_database(
    metrics: LogMetrics, db_path: str, host: str, port: int, user: str
) -> None:
    """
    Loads aggregated metrics into the SQLite database.

    Uses parameterized queries to safeguard against SQL injection vulnerabilities.

    Args:
        metrics: Log metrics containing error counts and API latency stats.
        db_path: Path to the SQLite database file.
        host: DB server host (for connection logging).
        port: DB server port (for connection logging).
        user: DB username (for connection logging).
    """
    print(f"Connecting to {host}:{port} as {user}...")

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

        # Safely insert errors with parameterized inputs
        for msg, count in metrics.errors.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        # Safely insert API latency averages with parameterized inputs
        for ep, times in metrics.api_metrics.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(metrics: LogMetrics, output_path: str) -> None:
    """
    Generates the HTML System Report summary.

    Args:
        metrics: Transformed log metrics.
        output_path: Path where the output HTML report should be saved.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    # Error summary section
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    # API Latency summary table
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics.api_metrics.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{str(round(avg, 1))}</td></tr>\n"
    out += "</table>\n"

    # Active session summary
    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """
    Executes the main ETL process.

    Extracts logs, transforms them to derive analytical statistics, loads them
    to the database, and produces the HTML summary report.
    """
    raw_lines = extract_log_lines(LOG_FILE)
    metrics = transform_log_lines(raw_lines)
    load_to_database(metrics, DB_PATH, DB_HOST, DB_PORT, DB_USER)
    generate_html_report(metrics, REPORT_FILE)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Generate mock log file for testing if it does not already exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_mock:
            f_mock.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_mock.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_mock.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_mock.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_mock.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_mock.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
