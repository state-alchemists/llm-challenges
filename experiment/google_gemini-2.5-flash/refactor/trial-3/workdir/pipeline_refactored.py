import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

def load_config() -> Dict[str, str]:
    """Loads configuration from environment variables."""
    config = {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE_PATH": os.getenv("LOG_FILE_PATH", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", "password123"),
    }
    return config

def connect_db(db_path: str) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database.
    
    Args:
        db_path: The path to the SQLite database file.
        
    Returns:
        A SQLite connection object.
    """
    print(f"Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    return conn

def create_tables(cursor: sqlite3.Cursor) -> None:
    """Creates the necessary tables in the database if they don't exist.
    
    Args:
        cursor: The database cursor object.
    """
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parses a single log line using regular expressions.

    Args:
        line: The log line to parse.

    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match a known pattern.
    """
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$")
    match = log_pattern.match(line)
    if not match:
        return None

    dt, level, message = match.groups()
    parsed_data: Dict[str, Any] = {"datetime": dt, "level": level}

    if level == "ERROR":
        parsed_data["type"] = "ERR"
        parsed_data["message"] = message.strip()
    elif level == "INFO":
        if "User" in message:
            user_pattern = re.compile(r"User (\d+) (logged in|logged out)")
            user_match = user_pattern.search(message)
            if user_match:
                uid, action = user_match.groups()
                parsed_data["type"] = "USR"
                parsed_data["uid"] = uid
                parsed_data["action"] = action
        elif "API" in message:
            api_pattern = re.compile(r"API (\S+) took (\d+)ms")
            api_match = api_pattern.search(message)
            if api_match:
                endpoint, duration = api_match.groups()
                parsed_data["type"] = "API"
                parsed_data["endpoint"] = endpoint
                parsed_data["duration_ms"] = int(duration)
    elif level == "WARN":
        parsed_data["type"] = "WARN"
        parsed_data["message"] = message.strip()

    return parsed_data

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """Reads and parses the entire log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
        - A list of parsed log entries (errors, warnings, user actions).
        - A dictionary of active sessions (uid: login_datetime).
        - A list of API call details.
    """
    log_entries: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    if parsed_line.get("type") == "ERR" or parsed_line.get("type") == "WARN":
                        log_entries.append(parsed_line)
                    elif parsed_line.get("type") == "USR":
                        uid = parsed_line["uid"]
                        dt = parsed_line["datetime"]
                        if "logged in" in parsed_line["action"]:
                            sessions[uid] = dt
                        elif "logged out" in parsed_line["action"] and uid in sessions:
                            sessions.pop(uid)
                        log_entries.append(parsed_line)
                    elif parsed_line.get("type") == "API":
                        api_calls.append(parsed_line)
    return log_entries, sessions, api_calls

def transform_error_data(log_entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregates error messages and their counts.

    Args:
        log_entries: A list of parsed log entries.

    Returns:
        A dictionary where keys are error messages and values are their counts.
    """
    error_summary: Dict[str, int] = {}
    for entry in log_entries:
        if entry.get("type") == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def transform_api_latency_data(api_calls: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Aggregates API call latencies by endpoint.

    Args:
        api_calls: A list of API call details.

    Returns:
        A dictionary where keys are API endpoints and values are lists of latencies in ms.
    """
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["duration_ms"])
    return endpoint_stats

def load_error_summary(cursor: sqlite3.Cursor, error_summary: Dict[str, int]) -> None:
    """Inserts error summary into the database using parameterized queries.

    Args:
        cursor: The database cursor object.
        error_summary: A dictionary of error messages and their counts.
    """
    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

def load_api_metrics(cursor: sqlite3.Cursor, endpoint_stats: Dict[str, List[int]]) -> None:
    """Inserts API metrics into the database using parameterized queries.

    Args:
        cursor: The database cursor object.
        endpoint_stats: A dictionary of API endpoints and their latencies.
    """
    for ep, times in endpoint_stats.items():
        if times:
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), ep, avg)
            )

def generate_report(error_summary: Dict[str, int], endpoint_stats: Dict[str, List[int]], active_sessions: Dict[str, str], output_file: str = "report.html") -> None:
    """Generates the HTML report.

    Args:
        error_summary: A dictionary of error messages and their counts.
        endpoint_stats: A dictionary of API endpoints and their latencies.
        active_sessions: A dictionary of currently active user sessions.
        output_file: The name of the output HTML file.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

    print(f"Report generated at {output_file}")

def main() -> None:
    """Main function to orchestrate the log processing and reporting."""
    config = load_config()
    db_path = config["DB_PATH"]
    log_file_path = config["LOG_FILE_PATH"]

    # Ensure log file exists for demonstration if not present
    if not os.path.exists(log_file_path):
        print(f"Log file not found at {log_file_path}. Creating a dummy one.")
        with open(log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /data/items took 120ms\n")

    log_entries, active_sessions, api_calls = extract_log_data(log_file_path)
    error_summary = transform_error_data(log_entries)
    endpoint_stats_raw = transform_api_latency_data(api_calls)

    conn = connect_db(db_path)
    cursor = conn.cursor()
    create_tables(cursor)

    load_error_summary(cursor, error_summary)
    load_api_metrics(cursor, endpoint_stats_raw) # Pass raw data, not average

    conn.commit()
    conn.close()

    generate_report(error_summary, endpoint_stats_raw, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
