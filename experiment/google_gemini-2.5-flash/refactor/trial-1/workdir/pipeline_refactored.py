import datetime
import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

class Config:
    """
    Configuration class to hold all environment variables required for the pipeline.
    """
    DB_PATH = os.environ.get("DB_PATH", "metrics.db")
    LOG_FILE_PATH = os.environ.get("LOG_FILE_PATH", "server.log")
    # DB_HOST, DB_PORT, DB_USER, DB_PASS are not directly used by sqlite3,
    # but kept for consistency if a different DB was to be used.
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "5432"))
    DB_USER = os.environ.get("DB_USER", "admin")
    DB_PASS = os.environ.get("DB_PASS", "password123")
    REPORT_FILE_PATH = os.environ.get("REPORT_FILE_PATH", "report.html")

def _read_log_file(log_file_path: str) -> List[str]:
    """
    Reads a log file and returns its content as a list of lines.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of strings, where each string is a line from the log file.
    """
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}")
        return []
    with open(log_file_path, "r") as f:
        return f.readlines()

def _parse_log_line(line: str) -> Optional[Dict]:
    """
    Parses a single log line using regex and extracts relevant information.

    Args:
        line: A single log line string.

    Returns:
        A dictionary containing parsed data (timestamp, level, message, user_id, action, endpoint, duration)
        or None if the line does not match any known log pattern.
    """
    # Regex for ERROR and WARN messages
    error_warn_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<level>ERROR|WARN) (?P<message>.*)$"
    )
    # Regex for INFO User messages
    user_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\w+) (?P<action>.*)$"
    )
    # Regex for INFO API messages
    api_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$"
    )

    if match := error_warn_pattern.match(line):
        return {
            "timestamp": match.group("timestamp"),
            "level": match.group("level"),
            "message": match.group("message").strip(),
        }
    elif match := user_pattern.match(line):
        return {
            "timestamp": match.group("timestamp"),
            "level": "INFO",
            "type": "USR",
            "user_id": match.group("user_id"),
            "action": match.group("action").strip(),
        }
    elif match := api_pattern.match(line):
        return {
            "timestamp": match.group("timestamp"),
            "level": "INFO",
            "type": "API",
            "endpoint": match.group("endpoint"),
            "duration_ms": int(match.group("duration")),
        }
    return None

def _process_events(parsed_events: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Processes a list of parsed log events and categorizes them.

    Args:
        parsed_events: A list of dictionaries, each representing a parsed log line.

    Returns:
        A tuple containing three lists: errors, api_calls, and user_sessions_events.
    """
    errors = []
    api_calls = []
    user_session_events = []

    for event in parsed_events:
        if event and event["level"] in ["ERROR", "WARN"]:
            errors.append(event)
        elif event and event.get("type") == "API":
            api_calls.append(event)
        elif event and event.get("type") == "USR":
            user_session_events.append(event)
    return errors, api_calls, user_session_events

def _analyze_errors(error_events: List[Dict]) -> Dict[str, int]:
    """
    Analyzes error events and returns a summary of error messages and their counts.

    Args:
        error_events: A list of dictionaries, each representing an error or warn log event.

    Returns:
        A dictionary where keys are error messages and values are their occurrence counts.
    """
    error_summary = {}
    for event in error_events:
        msg = event["message"]
        error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def _analyze_api_latency(api_call_events: List[Dict]) -> Dict[str, List[int]]:
    """
    Analyzes API call events and returns a dictionary of endpoint latencies.

    Args:
        api_call_events: A list of dictionaries, each representing an API call log event.

    Returns:
        A dictionary where keys are API endpoints and values are lists of their latencies in ms.
    """
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_call_events:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["duration_ms"])
    return endpoint_stats

def _calculate_active_sessions(user_session_events: List[Dict]) -> int:
    """
    Calculates the number of currently active sessions based on login/logout events.

    Args:
        user_session_events: A list of dictionaries, each representing a user session log event.

    Returns:
        The count of currently active sessions.
    """
    sessions = {}
    for event in user_session_events:
        uid = event["user_id"]
        action = event["action"]
        if "logged in" in action:
            sessions[uid] = event["timestamp"]
        elif "logged out" in action and uid in sessions:
            sessions.pop(uid)
    return len(sessions)

def _get_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    return sqlite3.connect(db_path)

def _init_db(conn: sqlite3.Connection):
    """
    Initializes the database by creating necessary tables if they don't exist.

    Args:
        conn: The database connection object.
    """
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()

def _insert_errors(conn: sqlite3.Connection, error_summary: Dict[str, int]):
    """
    Inserts error summary data into the database using parameterized queries.

    Args:
        conn: The database connection object.
        error_summary: A dictionary of error messages and their counts.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (current_time, msg, count))
    conn.commit()

def _insert_api_metrics(conn: sqlite3.Connection, endpoint_stats: Dict[str, List[int]]):
    """
    Inserts API latency metrics into the database using parameterized queries.

    Args:
        conn: The database connection object.
        endpoint_stats: A dictionary of API endpoints and lists of their latencies.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (current_time, ep, avg))
    conn.commit()

def _generate_report(error_summary: Dict[str, int], api_latency_stats: Dict[str, float], active_sessions_count: int) -> str:
    """
    Generates an HTML report string from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_latency_stats: A dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of active user sessions.

    Returns:
        A string containing the HTML report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg_ms in api_latency_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(avg_ms, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

def _write_report_file(report_content: str, output_file_path: str):
    """
    Writes the generated HTML report to a file.

    Args:
        report_content: The HTML content as a string.
        output_file_path: The path where the report file will be saved.
    """
    with open(output_file_path, "w") as f:
        f.write(report_content)

def run_pipeline():
    """
    Orchestrates the entire log processing and reporting pipeline.
    """
    print(f"Starting job at {datetime.datetime.now()}")

    # Extract
    log_lines = _read_log_file(Config.LOG_FILE_PATH)
    parsed_events = [_parse_log_line(line) for line in log_lines]
    parsed_events = [event for event in parsed_events if event is not None] # Filter out unparsed lines

    # Transform
    errors, api_calls, user_session_events = _process_events(parsed_events)
    error_summary = _analyze_errors(errors)
    endpoint_latencies = _analyze_api_latency(api_calls)
    active_sessions_count = _calculate_active_sessions(user_session_events)

    # Calculate average API latencies for reporting
    api_latency_stats_for_report = {
        ep: sum(times) / len(times) for ep, times in endpoint_latencies.items() if times
    }

    # Load (into DB)
    conn = None
    try:
        conn = _get_db_connection(Config.DB_PATH)
        _init_db(conn)
        _insert_errors(conn, error_summary)
        _insert_api_metrics(conn, endpoint_latencies)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

    # Load (into HTML report)
    html_report_content = _generate_report(error_summary, api_latency_stats_for_report, active_sessions_count)
    _write_report_file(html_report_content, Config.REPORT_FILE_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(Config.LOG_FILE_PATH):
        with open(Config.LOG_FILE_PATH, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:11:00 INFO API /products took 100ms\n")

    run_pipeline()