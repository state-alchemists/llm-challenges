import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

# Configuration Constants
METRICS_DB_PATH_ENV = "METRICS_DB_PATH"
SERVER_LOG_FILE_ENV = "SERVER_LOG_FILE"
REPORT_FILE_NAME = "report.html"

# Regex Patterns for log parsing
ERROR_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$")
INFO_USER_LOGIN_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\d+) logged in$")
INFO_USER_LOGOUT_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\d+) logged out$")
INFO_API_CALL_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$")
WARN_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$")

class Config:
    """Stores application configuration loaded from environment variables."""
    metrics_db_path: str
    server_log_file: str

    def __init__(self, metrics_db_path: str, server_log_file: str):
        self.metrics_db_path = metrics_db_path
        self.server_log_file = server_log_file

def get_config() -> Config:
    """
    Loads configuration from environment variables.

    Raises:
        ValueError: If a required environment variable is not set.

    Returns:
        Config: An object containing the application configuration.
    """
    metrics_db_path = os.getenv(METRICS_DB_PATH_ENV, "metrics.db")
    server_log_file = os.getenv(SERVER_LOG_FILE_ENV, "server.log")

    if not metrics_db_path:
        raise ValueError(f"Environment variable {METRICS_DB_PATH_ENV} not set.")
    if not server_log_file:
        raise ValueError(f"Environment variable {SERVER_LOG_FILE_ENV} not set.")

    return Config(metrics_db_path=metrics_db_path, server_log_file=server_log_file)

def parse_log_line(line: str) -> Dict[str, Any] | None:
    """
    Parses a single log line using regex patterns.

    Args:
        line (str): The log line to parse.

    Returns:
        Optional[Dict[str, Any]]: A dictionary with parsed log data, or None if the line doesn't match a known pattern.
    """
    if match := ERROR_PATTERN.match(line):
        return {"type": "ERROR", **match.groupdict()}
    elif match := INFO_USER_LOGIN_PATTERN.match(line):
        return {"type": "USER_LOGIN", **match.groupdict()}
    elif match := INFO_USER_LOGOUT_PATTERN.match(line):
        return {"type": "USER_LOGOUT", **match.groupdict()}
    elif match := INFO_API_CALL_PATTERN.match(line):
        data = match.groupdict()
        data["duration"] = int(data["duration"])
        return {"type": "API_CALL", **data}
    elif match := WARN_PATTERN.match(line):
        return {"type": "WARN", **match.groupdict()}
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, datetime.datetime]]:
    """
    Extracts structured data from the server log file.

    Args:
        log_file_path (str): The path to the server log file.

    Returns:
        Tuple[List[Dict[str, Any]], Dict[str, datetime.datetime]]:
            A tuple containing:
            - A list of all parsed log entries.
            - A dictionary of currently active sessions (user_id -> login_timestamp).
    """
    parsed_entries: List[Dict[str, Any]] = []
    active_sessions: Dict[str, datetime.datetime] = {}

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_entries, active_sessions

    with open(log_file_path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry:
                parsed_entries.append(entry)
                timestamp = datetime.datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")

                if entry["type"] == "USER_LOGIN":
                    active_sessions[entry["user_id"]] = timestamp
                elif entry["type"] == "USER_LOGOUT":
                    if entry["user_id"] in active_sessions:
                        active_sessions.pop(entry["user_id"])
    return parsed_entries, active_sessions

def transform_data(
    parsed_entries: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms raw parsed log entries into aggregated error summaries and API metrics.

    Args:
        parsed_entries (List[Dict[str, Any]]): A list of parsed log entries.

    Returns:
        Tuple[Dict[str, int], Dict[str, List[int]]]:
            A tuple containing:
            - A dictionary mapping error messages to their counts.
            - A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    error_summary: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}

    for entry in parsed_entries:
        if entry["type"] == "ERROR":
            message = entry["message"]
            error_summary[message] = error_summary.get(message, 0) + 1
        elif entry["type"] == "API_CALL":
            endpoint = entry["endpoint"]
            duration = entry["duration"]
            api_latencies.setdefault(endpoint, []).append(duration)
    return error_summary, api_latencies

def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Initializes the SQLite database connection and creates necessary tables.

    Args:
        db_path (str): The path to the SQLite database file.

    Returns:
        sqlite3.Connection: An active SQLite database connection.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn

def load_data_to_db(
    conn: sqlite3.Connection,
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]]
) -> None:
    """
    Loads transformed data into the database using parameterized queries.

    Args:
        conn (sqlite3.Connection): The database connection.
        error_summary (Dict[str, int]): Aggregated error messages and their counts.
        api_latencies (Dict[str, List[int]]): API endpoints and their latency lists.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert error summary
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                  (current_time, msg, count))

    # Insert API metrics
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                      (current_time, ep, avg))
    conn.commit()

def generate_html_report(
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_session_count: int
) -> str:
    """
    Generates the HTML content for the system report.

    Args:
        error_summary (Dict[str, int]): Aggregated error messages and their counts.
        api_latencies (Dict[str, List[int]]): API endpoints and their latency lists.
        active_session_count (int): The number of currently active user sessions.

    Returns:
        str: The complete HTML content of the report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

def write_report_file(file_path: str, content: str) -> None:
    """
    Writes the given content to a specified file.

    Args:
        file_path (str): The path to the output file.
        content (str): The content to write.
    """
    with open(file_path, "w") as f:
        f.write(content)
    print(f"Report written to {file_path}")

def main() -> None:
    """
    Main function to orchestrate the log processing and report generation.
    """
    print(f"Job started at {datetime.datetime.now()}")

    config = get_config()

    # For demonstration: create a dummy log file if it doesn't exist
    if not os.path.exists(config.server_log_file):
        print(f"Creating dummy log file: {config.server_log_file}")
        with open(config.server_log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:12:00 INFO User 101 logged in\n") # New user for active session test

    # E-T-L Process
    parsed_entries, active_sessions = extract_log_data(config.server_log_file)
    error_summary, api_latencies = transform_data(parsed_entries)

    conn = initialize_database(config.metrics_db_path)
    try:
        load_data_to_db(conn, error_summary, api_latencies)
    finally:
        conn.close()

    report_content = generate_html_report(error_summary, api_latencies, len(active_sessions))
    write_report_file(REPORT_FILE_NAME, report_content)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
