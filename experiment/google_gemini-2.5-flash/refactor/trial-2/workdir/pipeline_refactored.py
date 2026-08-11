'''
This script processes server logs, extracts relevant information,
stores aggregated data in a SQLite database, and generates an HTML report.
'''

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

# 1. Use environment variables for all config
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
# DB_HOST, DB_PORT, DB_USER, DB_PASS are not directly used by sqlite3, but kept for consistency
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex patterns for log parsing
ERROR_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$")
INFO_USER_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\w+) (?P<action>.*)$")
INFO_API_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$")
WARN_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$")

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """
    Extracts raw error messages, API calls, and session data from the log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing three lists:
        - raw_errors: List of dictionaries with 'timestamp' and 'message' for errors.
        - raw_api_calls: List of dictionaries with 'timestamp', 'endpoint', and 'duration' for API calls.
        - sessions: Dictionary mapping user_id to login timestamp for active sessions.
    """
    raw_errors: List[Dict[str, Any]] = []
    raw_api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return raw_errors, raw_api_calls, sessions

    with open(log_file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if error_match := ERROR_PATTERN.match(line):
                raw_errors.append({
                    "timestamp": error_match.group("timestamp"),
                    "message": error_match.group("message")
                })
            elif info_user_match := INFO_USER_PATTERN.match(line):
                user_id = info_user_match.group("user_id")
                action = info_user_match.group("action")
                timestamp = info_user_match.group("timestamp")
                if "logged in" in action:
                    sessions[user_id] = timestamp
                elif "logged out" in action and user_id in sessions:
                    sessions.pop(user_id)
            elif info_api_match := INFO_API_PATTERN.match(line):
                raw_api_calls.append({
                    "timestamp": info_api_match.group("timestamp"),
                    "endpoint": info_api_match.group("endpoint"),
                    "duration": int(info_api_match.group("duration"))
                })
            elif warn_match := WARN_PATTERN.match(line):
                # For now, warnings are just logged, not stored or reported in HTML
                pass

    return raw_errors, raw_api_calls, sessions

def transform_error_data(raw_errors: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Aggregates error messages and counts their occurrences.

    Args:
        raw_errors: A list of dictionaries, each representing an error log entry.

    Returns:
        A dictionary where keys are error messages and values are their counts.
    """
    error_summary: Dict[str, int] = {}
    for error in raw_errors:
        msg = error["message"]
        error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def transform_api_data(raw_api_calls: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """
    Groups API call durations by endpoint.

    Args:
        raw_api_calls: A list of dictionaries, each representing an API call log entry.

    Returns:
        A dictionary where keys are API endpoints and values are lists of durations in ms.
    """
    endpoint_latencies: Dict[str, List[int]] = {}
    for call in raw_api_calls:
        endpoint = call["endpoint"]
        endpoint_latencies.setdefault(endpoint, []).append(call["duration"])
    return endpoint_latencies

def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]]
) -> None:
    """
    Connects to the SQLite database and loads processed error and API metric data.
    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error messages and their counts.
        endpoint_latencies: A dictionary of API endpoints and their raw latencies.
    """
    print(f"Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create tables if they don't exist
    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Insert error summary data using parameterized queries
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (str(datetime.datetime.now()), msg, count),
        )

    # Calculate average API latency and insert into db using parameterized queries
    for ep, times in endpoint_latencies.items():
        if times:
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (str(datetime.datetime.now()), ep, avg),
            )

    conn.commit()
    conn.close()
    print("Data loaded to database successfully.")

def generate_report(
    error_summary: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report summarizing errors, API latencies, and active sessions.

    Args:
        error_summary: A dictionary of error messages and their counts.
        endpoint_latencies: A dictionary of API endpoints and their raw latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += """<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in endpoint_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"""<h2>Active Sessions</h2>
<p>{active_sessions_count} user(s) currently active</p>\n
</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")

def main() -> None:
    """
    Main function to orchestrate the log processing and report generation.
    """
    print(f"Job started at {datetime.datetime.now()}")

    raw_errors, raw_api_calls, sessions = extract_log_data(LOG_FILE)

    error_summary = transform_error_data(raw_errors)
    endpoint_latencies = transform_api_data(raw_api_calls)
    active_sessions_count = len(sessions)

    load_data_to_db(DB_PATH, error_summary, endpoint_latencies)
    generate_report(error_summary, endpoint_latencies, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # For development: create a dummy log file if it doesn't exist
    if not os.path.exists(LOG_FILE):
        print(f"Creating dummy log file: {LOG_FILE}")
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Another Database timeout\n") # Added another error for count testing
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:08:30 INFO API /data/items took 120ms\n") # Added another API call
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:11:00 INFO User 50 logged in\n") # Added another user session

    main()