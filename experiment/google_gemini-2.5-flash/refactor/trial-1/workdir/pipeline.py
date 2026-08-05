import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any

# --- Configuration ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
REPORT_FILE = os.getenv("REPORT_FILE", "report.html")
# DB_HOST, DB_PORT, DB_USER, DB_PASS are not directly used by sqlite3, but kept for completeness
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Regex Patterns for Log Parsing ---
ERROR_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$")
INFO_USER_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\w+) (?P<action>.*)$")
INFO_API_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$")
WARN_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$")

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the log file using regex patterns.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
        - A list of dictionaries for general log entries (errors, warnings, user actions).
        - A dictionary tracking active user sessions.
        - A list of dictionaries for API call metrics.
    """
    general_log_entries: List[Dict[str, Any]] = []
    active_sessions: Dict[str, str] = {}
    api_call_metrics: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return general_log_entries, active_sessions, api_call_metrics

    with open(log_file_path, "r") as f:
        for line in f:
            if error_match := ERROR_PATTERN.match(line):
                general_log_entries.append({
                    "timestamp": error_match.group("timestamp"),
                    "type": "ERR",
                    "message": error_match.group("message").strip()
                })
            elif user_match := INFO_USER_PATTERN.match(line):
                user_id = user_match.group("user_id")
                action = user_match.group("action").strip()
                timestamp = user_match.group("timestamp")
                if "logged in" in action:
                    active_sessions[user_id] = timestamp
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
                general_log_entries.append({
                    "timestamp": timestamp,
                    "type": "USR",
                    "user_id": user_id,
                    "action": action
                })
            elif api_match := INFO_API_PATTERN.match(line):
                api_call_metrics.append({
                    "timestamp": api_match.group("timestamp"),
                    "endpoint": api_match.group("endpoint"),
                    "duration_ms": int(api_match.group("duration"))
                })
            elif warn_match := WARN_PATTERN.match(line):
                general_log_entries.append({
                    "timestamp": warn_match.group("timestamp"),
                    "type": "WARN",
                    "message": warn_match.group("message").strip()
                })
            # else:
            #     print(f"Skipping unparseable line: {line.strip()}")

    return general_log_entries, active_sessions, api_call_metrics


def connect_db(db_path: str) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A SQLite database connection object.
    """
    print(f"Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Optional: access columns by name
    return conn


def setup_db(conn: sqlite3.Connection) -> None:
    """
    Sets up the necessary tables in the database.

    Args:
        conn: The database connection object.
    """
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
    """)
    conn.commit()


def process_errors(conn: sqlite3.Connection, general_log_entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Aggregates error messages and inserts their counts into the database.

    Args:
        conn: The database connection object.
        general_log_entries: A list of general log entries.

    Returns:
        A dictionary containing error messages and their aggregated counts.
    """
    error_counts: Dict[str, int] = {}
    for entry in general_log_entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    c = conn.cursor()
    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )
    conn.commit()
    return error_counts


def process_api_metrics(conn: sqlite3.Connection, api_call_metrics: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculates average API latency per endpoint and inserts into the database.

    Args:
        conn: The database connection object.
        api_call_metrics: A list of API call metrics.

    Returns:
        A dictionary containing API endpoints and their average latencies.
    """
    endpoint_durations: Dict[str, List[int]] = {}
    for call in api_call_metrics:
        ep = call["endpoint"]
        endpoint_durations.setdefault(ep, []).append(call["duration_ms"])

    endpoint_avg_latencies: Dict[str, float] = {}
    c = conn.cursor()
    for ep, times in endpoint_durations.items():
        avg = sum(times) / len(times)
        endpoint_avg_latencies[ep] = avg
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )
    conn.commit()
    return endpoint_avg_latencies


def generate_report(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, float],
    active_sessions_count: int,
    output_file: str
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_latency_stats: A dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of active user sessions.
        output_file: The path to save the HTML report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")


def main():
    """
    Main function to orchestrate the log processing and report generation pipeline.
    """
    # 1. Extract
    general_log_entries, active_sessions, api_call_metrics = extract_log_data(LOG_FILE)

    # 2. Transform and Load
    conn = None
    try:
        conn = connect_db(DB_PATH)
        setup_db(conn)
        error_summary = process_errors(conn, general_log_entries)
        api_latency_stats = process_api_metrics(conn, api_call_metrics)
    finally:
        if conn:
            conn.close()

    # 3. Report
    generate_report(error_summary, api_latency_stats, len(active_sessions), REPORT_FILE)
    
    print("Job finished at " + str(datetime.datetime.now()))


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

