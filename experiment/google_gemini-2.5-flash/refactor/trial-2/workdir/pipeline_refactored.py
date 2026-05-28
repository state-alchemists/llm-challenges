import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

def parse_log_line(line: str) -> Dict[str, Any] | None:
    """
    Parses a single log line using regular expressions.

    Args:
        line: The log line string to parse.

    Returns:
        A dictionary containing parsed log data if successful, otherwise None.
    """
    # Regex to capture timestamp, level, and the rest of the message
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$", line)
    if not match:
        return None

    timestamp_str, level, message = match.groups()
    parsed_data = {
        "timestamp": timestamp_str,
        "level": level,
        "message": message.strip()
    }

    if level == "ERROR":
        return {**parsed_data, "type": "ERR"}
    elif level == "WARN":
        return {**parsed_data, "type": "WARN"}
    elif level == "INFO":
        if "User" in message:
            user_match = re.match(r".*User (\d+) (.*)", message)
            if user_match:
                uid, action = user_match.groups()
                return {**parsed_data, "type": "USR", "uid": uid, "action": action.strip()}
        elif "API" in message:
            api_match = re.match(r".*API (/[\w/]+)(?: took (\d+)ms)?", message)
            if api_match:
                endpoint, duration_str = api_match.groups()
                duration = int(duration_str) if duration_str else 0
                return {**parsed_data, "type": "API", "endpoint": endpoint, "duration_ms": duration}
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts relevant data from the log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of parsed log entries.
            - A dictionary of active user sessions.
            - A list of API call details.
    """
    parsed_entries: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                data = parse_log_line(line)
                if data:
                    parsed_entries.append(data)
                    if data["type"] == "USR":
                        uid = data["uid"]
                        timestamp = data["timestamp"]
                        if "logged in" in data["action"]:
                            sessions[uid] = timestamp
                        elif "logged out" in data["action"] and uid in sessions:
                            sessions.pop(uid)
                    elif data["type"] == "API":
                        api_calls.append({
                            "timestamp": data["timestamp"],
                            "endpoint": data["endpoint"],
                            "ms": data["duration_ms"]
                        })
    return parsed_entries, sessions, api_calls

def transform_data(
    parsed_entries: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms the raw log data into structured error and API statistics.

    Args:
        parsed_entries: List of parsed log entries.
        api_calls: List of API call details.

    Returns:
        A tuple containing:
            - A dictionary of error message counts.
            - A dictionary mapping API endpoints to a list of durations.
    """
    error_summary: Dict[str, int] = {}
    for entry in parsed_entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint = call["endpoint"]
        endpoint_stats.setdefault(endpoint, []).append(call["ms"])
    
    return error_summary, endpoint_stats

def load_data_to_db(
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
    db_pass: str
) -> None:
    """
    Loads the processed data into an SQLite database.

    Args:
        error_summary: Dictionary of error message counts.
        endpoint_stats: Dictionary mapping API endpoints to a list of durations.
        db_path: Path to the SQLite database file.
        db_host: Database host (not used for SQLite but kept for consistency).
        db_port: Database port (not used for SQLite but kept for consistency).
        db_user: Database user (not used for SQLite but kept for consistency).
        db_pass: Database password (not used for SQLite but kept for consistency).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, count)
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ep, avg)
        )

    conn.commit()
    conn.close()

def generate_report(
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: Dictionary of error message counts.
        endpoint_stats: Dictionary mapping API endpoints to a list of durations.
        active_sessions_count: The number of active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

def main():
    """
    Main function to orchestrate the log processing and reporting.
    """
    parsed_entries, sessions, api_calls = extract_log_data(LOG_FILE)
    error_summary, endpoint_stats = transform_data(parsed_entries, api_calls)
    load_data_to_db(error_summary, endpoint_stats, DB_PATH, DB_HOST, DB_PORT, DB_USER, DB_PASS)
    generate_report(error_summary, endpoint_stats, len(sessions))
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        log_content = """2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Another error occurred
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
2024-01-01 12:11:00 INFO API /data/items took 120ms
2024-01-01 12:12:00 INFO User 101 logged in
2024-01-01 12:15:00 INFO API /status took 50ms
"""
        with open(LOG_FILE, "w") as f:
            f.write(log_content)
    main()
