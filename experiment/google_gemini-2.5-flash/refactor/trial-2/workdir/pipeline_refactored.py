import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple

# Load configuration from environment variables with sensible defaults
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_log_data(log_file_path: str) -> List[Dict]:
    """
    Reads the log file and parses each line using regular expressions.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    parsed_logs = []
    log_patterns = {
        "ERROR": re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$"),
        "INFO_USER": re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\w+) (?P<action>.*)$"),
        "INFO_API": re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$"),
        "WARN": re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$"),
    }

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            for log_type, pattern in log_patterns.items():
                match = pattern.match(line)
                if match:
                    log_entry = match.groupdict()
                    log_entry["type"] = log_type
                    parsed_logs.append(log_entry)
                    break
    return parsed_logs


def transform_data(parsed_logs: List[Dict]) -> Tuple[Dict, Dict, int]:
    """
    Processes raw log entries to aggregate errors, API call latencies, and active sessions.

    Args:
        parsed_logs: A list of dictionaries, each representing a parsed log entry.

    Returns:
        A tuple containing:
            - error_summary: A dictionary with error messages and their counts.
            - api_latency_stats: A dictionary with API endpoints and a list of their latencies.
            - active_sessions_count: The number of currently active user sessions.
    """
    error_summary: Dict[str, int] = {}
    api_latency_stats: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {} # user_id -> login_timestamp
    unique_active_users: set = set() # To track all unique users who logged in

    for entry in parsed_logs:
        log_type = entry.get("type")
        
        if log_type == "ERROR":
            message = entry.get("message")
            if message:
                error_summary[message] = error_summary.get(message, 0) + 1
        elif log_type == "INFO_USER":
            user_id = entry.get("user_id")
            action = entry.get("action")
            if user_id and action:
                if "logged in" in action:
                    sessions[user_id] = entry.get("timestamp", "")
                    unique_active_users.add(user_id) # Add user to the set of unique active users
                elif "logged out" in action and user_id in sessions:
                    sessions.pop(user_id)
        elif log_type == "INFO_API":
            endpoint = entry.get("endpoint")
            duration_str = entry.get("duration")
            if endpoint and duration_str:
                try:
                    duration = int(duration_str)
                    api_latency_stats.setdefault(endpoint, []).append(duration)
                except ValueError:
                    print(f"Warning: Could not parse API duration '{duration_str}' for endpoint '{endpoint}'")
    
    return error_summary, api_latency_stats, len(unique_active_users)


def load_data(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
) -> None:
    """
    Connects to the database, creates tables if they don't exist, and inserts the processed data.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary with error messages and their counts.
        api_latency_stats: A dictionary with API endpoints and a list of their latencies.
    """
    print(f"Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert error summary
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (current_time, msg, count))

    # Insert API latency metrics
    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times) if times else 0
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (current_time, ep, avg))

    conn.commit()
    conn.close()
    print("Data loaded into database successfully.")


def generate_report(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
    active_sessions_count: int,
    report_file_path: str,
) -> None:
    """
    Generates an HTML report based on the aggregated data.

    Args:
        error_summary: A dictionary with error messages and their counts.
        api_latency_stats: A dictionary with API endpoints and a list of their latencies.
        active_sessions_count: The number of currently active user sessions.
        report_file_path: The path where the HTML report will be saved.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_file_path, "w") as f:
        f.write(out)
    print(f"Report generated at {report_file_path}")


def main():
    """
    Orchestrates the log processing, data loading, and report generation.
    """
    print(f"Starting log processing at {datetime.datetime.now()}")

    # Extract
    parsed_logs = extract_log_data(LOG_FILE)

    # Transform
    error_summary, api_latency_stats, active_sessions_count = transform_data(parsed_logs)

    # Load
    # DB_HOST, DB_PORT, DB_USER, DB_PASS are not directly used by sqlite3.connect
    # but kept for consistency with the original request regarding config via env vars.
    load_data(DB_PATH, error_summary, api_latency_stats)

    # Generate Report
    generate_report(error_summary, api_latency_stats, active_sessions_count, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")




if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()