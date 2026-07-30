import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple, Optional

# 1. Use environment variables for all config
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex for log line parsing
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<message>[^\n]*)$"
)
INFO_USER_PATTERN = re.compile(r"User (?P<user_id>\w+) (?P<action>.*)")
INFO_API_PATTERN = re.compile(r"API (?P<endpoint>\S+) took (?P<duration>\d+)ms")


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex and extracts relevant information.

    Args:
        line: The log line string to parse.

    Returns:
        A dictionary containing parsed log data (timestamp, level, message, etc.)
        or None if the line does not match the expected format.
    """
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    data = match.groupdict()
    log_level = data["level"]
    message = data["message"]

    if log_level == "INFO":
        user_match = INFO_USER_PATTERN.match(message)
        if user_match:
            user_data = user_match.groupdict()
            return {
                "timestamp": data["timestamp"],
                "level": log_level,
                "type": "USR",
                "user_id": user_data["user_id"],
                "action": user_data["action"].strip(),
            }

        api_match = INFO_API_PATTERN.match(message)
        if api_match:
            api_data = api_match.groupdict()
            return {
                "timestamp": data["timestamp"],
                "level": log_level,
                "type": "API",
                "endpoint": api_data["endpoint"],
                "duration_ms": int(api_data["duration"]),
            }
    elif log_level == "ERROR":
        return {
            "timestamp": data["timestamp"],
            "level": log_level,
            "type": "ERR",
            "message": message.strip(),
        }
    elif log_level == "WARN":
        return {
            "timestamp": data["timestamp"],
            "level": log_level,
            "type": "WARN",
            "message": message.strip(),
        }
    return None


def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts and parses log data from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed log entry.
    """
    parsed_logs: List[Dict[str, Any]] = []
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    parsed_logs.append(parsed_line)
    return parsed_logs


def process_error_logs(parsed_logs: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Processes parsed logs to summarize error messages and their counts.

    Args:
        parsed_logs: A list of dictionaries representing parsed log entries.

    Returns:
        A dictionary where keys are error messages and values are their occurrence counts.
    """
    error_summary: Dict[str, int] = {}
    for log_entry in parsed_logs:
        if log_entry.get("type") == "ERR":
            message = log_entry.get("message")
            if message:
                error_summary[message] = error_summary.get(message, 0) + 1
    return error_summary


def process_api_metrics(parsed_logs: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """
    Processes parsed logs to gather API call durations for each endpoint.

    Args:
        parsed_logs: A list of dictionaries representing parsed log entries.

    Returns:
        A dictionary where keys are API endpoints and values are lists of call durations in ms.
    """
    api_calls: Dict[str, List[int]] = {}
    for log_entry in parsed_logs:
        if log_entry.get("type") == "API":
            endpoint = log_entry.get("endpoint")
            duration = log_entry.get("duration_ms")
            if endpoint and duration is not None:
                api_calls.setdefault(endpoint, []).append(duration)
    return api_calls


def track_user_sessions(parsed_logs: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Tracks active user sessions based on login and logout events.

    Args:
        parsed_logs: A list of dictionaries representing parsed log entries.

    Returns:
        A dictionary where keys are user IDs and values are their login timestamps.
    """
    active_sessions: Dict[str, str] = {}
    for log_entry in parsed_logs:
        if log_entry.get("type") == "USR":
            user_id = log_entry.get("user_id")
            action = log_entry.get("action")
            if user_id and action:
                if "logged in" in action:
                    active_sessions[user_id] = log_entry["timestamp"]
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
    return active_sessions


def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Initializes the SQLite database and creates necessary tables if they don't exist.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        An SQLite database connection object.
    """
    print(f"Connecting to database: {db_path}...")
    # In a real-world scenario, DB_HOST, DB_PORT, DB_USER, DB_PASS would be used
    # to connect to a PostgreSQL or similar database. For sqlite, only db_path is relevant.
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn


def insert_error_summary(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """
    Inserts error summary data into the 'errors' table using parameterized queries.

    Args:
        conn: The SQLite database connection object.
        error_summary: A dictionary of error messages and their counts.
    """
    c = conn.cursor()
    for msg, count in error_summary.items():
        # 2. Fix the SQL injection - use parameterized queries
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )
    conn.commit()


def insert_api_latency(conn: sqlite3.Connection, api_calls: Dict[str, List[int]]) -> None:
    """
    Calculates average API latency and inserts it into the 'api_metrics' table
    using parameterized queries.

    Args:
        conn: The SQLite database connection object.
        api_calls: A dictionary of API endpoints and their call durations.
    """
    c = conn.cursor()
    for ep, times in api_calls.items():
        if times:
            avg = sum(times) / len(times)
            # 2. Fix the SQL injection - use parameterized queries
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), ep, avg)
            )
    conn.commit()


def generate_report_html(
    error_summary: Dict[str, int],
    api_calls: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report summarizing error counts, API latencies, and active sessions.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_calls: A dictionary of API endpoints and their call durations.
        active_sessions: A dictionary of active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += """</ul>

<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in api_calls.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += """</table>

<h2>Active Sessions</h2>
"""
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\\n"
    out += """</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated to {output_file}")


def main() -> None:
    """
    Orchestrates the log processing, data transformation, database loading,
    and HTML report generation.
    """
    # Extract
    parsed_logs = extract_log_data(LOG_FILE)

    # Transform
    error_summary = process_error_logs(parsed_logs)
    api_latency_data = process_api_metrics(parsed_logs)
    active_sessions = track_user_sessions(parsed_logs)

    # Load
    conn = None
    try:
        conn = initialize_database(DB_PATH)
        insert_error_summary(conn, error_summary)
        insert_api_latency(conn, api_latency_data)
    finally:
        if conn:
            conn.close()

    generate_report_html(error_summary, api_latency_data, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("""
2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Database timeout
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
2024-01-01 12:15:00 INFO API /data/stream took 120ms
2024-01-01 12:20:00 INFO User 10 logged in
""")
    main()
