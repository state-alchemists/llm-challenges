'''
Refactored pipeline script for processing server logs and generating a report.

This script reads server logs, parses them for errors, API calls, and user sessions,
stores aggregated metrics in an SQLite database, and generates an HTML report.

It addresses several security and maintainability concerns from the original script:
- Configuration via environment variables.
- SQL injection prevention using parameterized queries.
- Modularized logic following Extract, Transform, Load (ETL) principles.
- Robust log parsing with regular expressions.
- Comprehensive type hints and docstrings for improved readability and maintainability.
'''

import datetime
import os
import re
import sqlite3
from typing import List, Dict, Tuple, Optional, Any

# --- Configuration --- #
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
REPORT_FILE = os.getenv("REPORT_FILE", "report.html")
# For external database connections, these would be used. For SQLite, DB_PATH is sufficient.
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = int(os.getenv("DB_PORT", "5432"))
# DB_USER = os.getenv("DB_USER", "admin")
# DB_PASS = os.getenv("DB_PASS", "password123")

# --- Regex Patterns for Log Parsing --- #
# Generic log line pattern to capture datetime and level
LOG_PATTERN = re.compile(
    r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|WARN|ERROR) "
    r"(?P<message>.*)$"
)

# Specific patterns for different message types
ERROR_WARN_MESSAGE_PATTERN = re.compile(
    r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN) "
    r"(?P<message>.*)$"
)

USER_ACTION_PATTERN = re.compile(
    r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User "
    r"(?P<uid>\d+) "
    r"(?P<action>.*)$"
)

API_CALL_PATTERN = re.compile(
    r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API "
    r"(?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex patterns to extract structured data.

    Args:
        line: A single string line from the log file.

    Returns:
        A dictionary containing parsed log data (datetime, level, message, etc.)
        or None if the line does not match any known pattern.
    """
    if match := ERROR_WARN_MESSAGE_PATTERN.match(line):
        return {
            "datetime": match.group("datetime"),
            "type": "ERROR" if match.group("level") == "ERROR" else "WARN",
            "message": match.group("message").strip(),
        }
    elif match := USER_ACTION_PATTERN.match(line):
        return {
            "datetime": match.group("datetime"),
            "type": "USER_ACTION",
            "uid": match.group("uid"),
            "action": match.group("action").strip(),
        }
    elif match := API_CALL_PATTERN.match(line):
        return {
            "datetime": match.group("datetime"),
            "type": "API_CALL",
            "endpoint": match.group("endpoint"),
            "duration_ms": int(match.group("duration")),
        }
    return None


def extract_logs(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the log file by reading and parsing each line.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
        - d_list: A list of dictionaries for errors, warnings, and user actions.
        - active_sessions: A dictionary tracking currently active user sessions.
        - api_calls: A list of dictionaries for API call metrics.
    """
    d_list: List[Dict[str, Any]] = []
    active_sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        print(f"Warning: Log file not found at {log_file_path}")
        return d_list, active_sessions, api_calls

    with open(log_file_path, "r") as f:
        for line in f:
            parsed_data = parse_log_line(line)
            if parsed_data:
                if parsed_data["type"] in ["ERROR", "WARN"]:
                    d_list.append(parsed_data)
                elif parsed_data["type"] == "USER_ACTION":
                    uid = parsed_data["uid"]
                    action = parsed_data["action"]
                    if "logged in" in action:
                        active_sessions[uid] = parsed_data["datetime"]
                    elif "logged out" in action and uid in active_sessions:
                        active_sessions.pop(uid)
                    d_list.append(parsed_data)
                elif parsed_data["type"] == "API_CALL":
                    api_calls.append(parsed_data)
    return d_list, active_sessions, api_calls


def transform_data(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms the extracted log data into summarized metrics.

    Args:
        d_list: A list of dictionaries for errors, warnings, and user actions.
        api_calls: A list of dictionaries for API call metrics.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    error_summary: Dict[str, int] = {}
    for entry in d_list:
        if entry["type"] == "ERROR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    api_latency_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint = call["endpoint"]
        api_latency_stats.setdefault(endpoint, []).append(call["duration_ms"])

    return error_summary, api_latency_stats


def load_to_db(db_path: str, error_summary: Dict[str, int], api_latency_stats: Dict[str, List[int]]):
    """
    Loads the transformed data into an SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary mapping error messages to their counts.
        api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        current_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (current_dt, msg, count),
            )

        for ep, times in api_latency_stats.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (current_dt, ep, avg),
                )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()


def generate_report(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
    active_sessions_count: int,
    report_file_path: str,
):
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary mapping error messages to their counts.
        api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
        active_sessions_count: The number of currently active user sessions.
        report_file_path: The path where the HTML report will be saved.
    """
    out = """
<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency_stats.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_file_path, "w") as f:
        f.write(out)


def main():
    """
    Main function to run the log processing pipeline.
    """
    print(f"Starting log processing pipeline at {datetime.datetime.now()}...")

    # 1. Extract
    d_list, active_sessions, api_calls = extract_logs(LOG_FILE)
    print(f"Extracted {len(d_list) + len(api_calls)} log entries.")

    # 2. Transform
    error_summary, api_latency_stats = transform_data(d_list, api_calls)
    print("Transformed data into summaries.")

    # 3. Load to DB
    print(f"Connecting to SQLite DB at {DB_PATH}...")
    load_to_db(DB_PATH, error_summary, api_latency_stats)
    print("Loaded metrics to database.")

    # 4. Generate Report
    generate_report(error_summary, api_latency_stats, len(active_sessions), REPORT_FILE)
    print(f"Generated report to {REPORT_FILE}.")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for testing purposes
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    main()
