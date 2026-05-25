import datetime
import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

# Configuration through environment variables
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")  # Example usage, though not utilized in SQLite
DB_PORT = os.environ.get("DB_PORT", "5432")       # Example usage, though not utilized in SQLite
DB_USER = os.environ.get("DB_USER", "admin")      # Example usage, though not utilized in SQLite
DB_PASS = os.environ.get("DB_PASS", "password123") # Example usage, though not utilized in SQLite


# Extract step: Read and parse logs
def extract_logs(filepath: str) -> Tuple[List[str], List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Reads log file and extracts errors, user sessions, and API call metrics.

    Args:
        filepath (str): Path to log file.

    Returns:
        Tuple[List[str], List[Dict[str, str]], List[Dict[str, str]]]:
        List of errors, session logs, and API call metrics.
    """
    error_logs = []
    session_logs = {}
    api_calls = []

    with open(filepath, "r") as f:
        log_lines = f.readlines()

    error_pattern = re.compile(r"(?P<datetime>\S+ \S+) ERROR (?P<message>.+)")
    session_pattern = re.compile(r"(?P<datetime>\S+ \S+) INFO User (?P<userid>\d+) (?P<action>.+)")
    api_pattern = re.compile(r"(?P<datetime>\S+ \S+) INFO API (?P<endpoint>\S+) took (?P<duration>\d+)ms")

    for line in log_lines:
        if error_match := error_pattern.match(line):
            error_logs.append(error_match.groupdict())
        elif session_match := session_pattern.match(line):
            session_data = session_match.groupdict()
            if "logged in" in session_data['action']:
                session_logs[session_data['userid']] = session_data['datetime']
            elif "logged out" in session_data['action']:
                session_logs.pop(session_data['userid'], None)
        elif api_match := api_pattern.match(line):
            api_calls.append(api_match.groupdict())

    return error_logs, list(session_logs.values()), api_calls


def transform_data(errors: List[str], sessions: List[str], api_calls: List[Dict[str, str]]) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms raw log data into structured data for database insertion.

    Args:
        errors (List[str]): List of error log messages.
        sessions (List[str]): List of active session timestamps.
        api_calls (List[Dict[str, str]]): List of API call logs.

    Returns:
        Tuple[Dict[str, int], Dict[str, List[int]]]:
        Summary of error occurrences and API metrics.
    """
    error_summary = {}
    api_metrics = {}

    for error in errors:
        message = error['message']
        if message in error_summary:
            error_summary[message] += 1
        else:
            error_summary[message] = 1

    for call in api_calls:
        endpoint = call['endpoint']
        duration = int(call['duration'])
        if endpoint not in api_metrics:
            api_metrics[endpoint] = []
        api_metrics[endpoint].append(duration)

    return error_summary, api_metrics


def load_data(conn: sqlite3.Connection, error_summary: Dict[str, int], api_metrics: Dict[str, List[int]], active_sessions_count: int) -> None:
    """
    Inserts transformed data into the database and generates a report.

    Args:
        conn (sqlite3.Connection): SQLite connection object.
        error_summary (Dict[str, int]): Summary of error occurrences.
        api_metrics (Dict[str, List[int]]): API call metrics data.
        active_sessions_count (int): Count of active sessions.
    """
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    current_time = datetime.datetime.now().isoformat()

    for message, count in error_summary.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                  (current_time, message, count))

    for endpoint, durations in api_metrics.items():
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                  (current_time, endpoint, avg_duration))

    conn.commit()

    generate_report(error_summary, api_metrics, active_sessions_count)


def generate_report(errors: Dict[str, int], api_metrics: Dict[str, List[int]], active_sessions_count: int) -> None:
    """
    Generates and writes an HTML report file summarizing the data.

    Args:
        errors (Dict[str, int]): Summary of error occurrences.
        api_metrics (Dict[str, List[int]]): API call metrics.
        active_sessions_count (int): Count of active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, durations in api_metrics.items():
        avg = sum(durations) / len(durations) if durations else 0.0
        out += f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        errors, sessions, api_calls = extract_logs(LOG_FILE)
        error_summary, api_metrics = transform_data(errors, sessions, api_calls)
        load_data(conn, error_summary, api_metrics, len(sessions))
    finally:
        conn.close()
        print("Job finished at", datetime.datetime.now())
