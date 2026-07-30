import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Iterator, Optional, Any

# 1. Use environment variables for all config
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_FILE = os.getenv("REPORT_FILE", "report.html")

# Regex for log line parsing
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>(INFO|WARN|ERROR)) "
    r"(?P<message>.*)$"
)

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex and extracts relevant information.

    Args:
        line: The log line string to parse.

    Returns:
        A dictionary containing parsed log data (timestamp, level, message)
        or None if the line does not match the expected pattern.
    """
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    data = match.groupdict()
    level = data["level"]
    message = data["message"]

    parsed_entry: Dict[str, Any] = {
        "timestamp": data["timestamp"],
        "level": level,
        "message": message.strip(),
        "type": level, # Default type for now, refined below
    }

    if level == "INFO":
        if "User" in message:
            user_match = re.search(r"User (\d+) (.*)", message)
            if user_match:
                parsed_entry["type"] = "USR"
                parsed_entry["user_id"] = user_match.group(1)
                parsed_entry["action"] = user_match.group(2).strip()
        elif "API" in message:
            api_match = re.search(r"API (\S+) took (\d+)ms", message)
            if api_match:
                parsed_entry["type"] = "API"
                parsed_entry["endpoint"] = api_match.group(1)
                parsed_entry["duration_ms"] = int(api_match.group(2))
    elif level == "ERROR":
        parsed_entry["type"] = "ERR"
    elif level == "WARN":
        parsed_entry["type"] = "WARN"

    return parsed_entry


def read_log_file(log_file_path: str) -> Iterator[Dict[str, Any]]:
    """
    Reads a log file line by line and yields parsed log entries.

    Args:
        log_file_path: The path to the log file.

    Yields:
        Parsed log entry dictionaries.
    """
    if not os.path.exists(log_file_path):
        print(f"Warning: Log file not found at {log_file_path}")
        return

    with open(log_file_path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry:
                yield entry


def process_log_entries(
    log_entries: Iterator[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes a stream of parsed log entries to aggregate error counts,
    API call latencies, and track active sessions.

    Args:
        log_entries: An iterator of parsed log entry dictionaries.

    Returns:
        A tuple containing:
        - error_summary (Dict[str, int]): Count of each unique error message.
        - api_metrics (Dict[str, List[int]]): List of latencies for each API endpoint.
        - active_sessions (int): Current count of active user sessions.
    """
    error_summary: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {} # user_id -> login_timestamp

    for entry in log_entries:
        entry_type = entry.get("type")
        if entry_type == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif entry_type == "API":
            endpoint = entry["endpoint"]
            duration = entry["duration_ms"]
            api_metrics.setdefault(endpoint, []).append(duration)
        elif entry_type == "USR":
            user_id = entry["user_id"]
            action = entry["action"]
            if "logged in" in action:
                sessions[user_id] = entry["timestamp"]
            elif "logged out" in action and user_id in sessions:
                sessions.pop(user_id)


    return error_summary, api_metrics, len(sessions)


def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Connects to the SQLite database and creates necessary tables if they don't exist.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A connection object to the SQLite database.
    """
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn


def insert_error_summary(conn: sqlite3.Connection, error_summary: Dict[str, int]):
    """
    Inserts error summary data into the database using parameterized queries.

    Args:
        conn: The database connection object.
        error_summary: A dictionary mapping error messages to their counts.
    """
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count)
        )
    conn.commit()


def insert_api_metrics(conn: sqlite3.Connection, api_metrics: Dict[str, List[int]]):
    """
    Calculates average API latency and inserts the metrics into the database
    using parameterized queries.

    Args:
        conn: The database connection object.
        api_metrics: A dictionary mapping API endpoints to a list of their latencies.
    """
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for ep, times in api_metrics.items():
        if times:
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg)
            )
    conn.commit()


def generate_report(
    error_summary: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_sessions: int,
    output_file: str
):
    """
    Generates an HTML report summarizing the system's status.

    Args:
        error_summary: A dictionary mapping error messages to their counts.
        api_metrics: A dictionary mapping API endpoints to a list of their latencies.
        active_sessions: The current count of active user sessions.
        output_file: The path where the HTML report will be saved.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated at {output_file}")


def main():
    """
    Main function to orchestrate the log processing and report generation.
    """
    print(f"Starting job at {datetime.datetime.now()}")

    # E - Extract
    log_entries_iterator = read_log_file(LOG_FILE)

    # T - Transform
    error_summary, api_metrics, active_sessions = process_log_entries(log_entries_iterator)

    # L - Load
    conn = None
    try:
        conn = initialize_database(DB_PATH)
        insert_error_summary(conn, error_summary)
        insert_api_metrics(conn, api_metrics)
    finally:
        if conn:
            conn.close()

    generate_report(error_summary, api_metrics, active_sessions, REPORT_FILE)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file for testing if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("""2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Database timeout
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
2024-01-01 12:15:00 INFO API /data/items took 120ms
2024-01-01 12:16:00 ERROR Another database error
""")

    main()
