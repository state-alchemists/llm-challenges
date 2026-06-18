import datetime
import os
import sqlite3
import re
from typing import Dict, List, Optional, Tuple, TypedDict

class LogEntry(TypedDict):
    timestamp: str
    level: str
    message: Optional[str]
    user_id: Optional[str]
    action: Optional[str]
    endpoint: Optional[str]
    duration_ms: Optional[int]

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

def parse_log_line(line: str) -> Optional[LogEntry]:
    """
    Parses a single log line using regular expressions.

    Args:
        line: The log line string to parse.

    Returns:
        A LogEntry TypedDict if the line is successfully parsed, None otherwise.
    """
    error_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$'')
    user_info_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\w+) (.*)$'')
    api_info_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$''')
    warn_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$'')

    error_match = error_pattern.match(line)
    if error_match:
        return LogEntry(
            timestamp=error_match.group(1),
            level="ERROR",
            message=error_match.group(2).strip(),
            user_id=None,
            action=None,
            endpoint=None,
            duration_ms=None,
        )

    user_info_match = user_info_pattern.match(line)
    if user_info_match:
        return LogEntry(
            timestamp=user_info_match.group(1),
            level="INFO",
            user_id=user_info_match.group(2),
            action=user_info_match.group(3).strip(),
            message=None,
            endpoint=None,
            duration_ms=None,
        )

    api_info_match = api_info_pattern.match(line)
    if api_info_match:
        return LogEntry(
            timestamp=api_info_match.group(1),
            level="INFO",
            endpoint=api_info_match.group(2),
            duration_ms=int(api_info_match.group(3)),
            message=None,
            user_id=None,
            action=None,
        )

    warn_match = warn_pattern.match(line)
    if warn_match:
        return LogEntry(
            timestamp=warn_match.group(1),
            level="WARN",
            message=warn_match.group(2).strip(),
            user_id=None,
            action=None,
            endpoint=None,
            duration_ms=None,
        )

    return None

def read_log_file(log_file_path: str) -> List[LogEntry]:
    """
    Reads a log file, parses each line, and returns a list of LogEntry objects.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of parsed LogEntry objects.
    """
    log_entries: List[LogEntry] = []
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                entry = parse_log_line(line)
                if entry:
                    log_entries.append(entry)
    return log_entries

def process_log_entries(
    log_entries: List[LogEntry]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """
    Processes parsed log entries to aggregate errors, API calls, and user sessions.

    Args:
        log_entries: A list of parsed LogEntry objects.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - api_calls_raw: A dictionary mapping API endpoints to a list of their durations.
        - sessions: A dictionary tracking active user sessions (user_id -> login_timestamp).
    """
    error_summary: Dict[str, int] = {}
    api_calls_raw: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in log_entries:
        if entry["level"] == "ERROR" and entry["message"] is not None:
            error_summary[entry["message"]] = error_summary.get(entry["message"], 0) + 1
        elif entry["level"] == "INFO":
            if entry["user_id"] is not None and entry["action"] is not None:
                if "logged in" in entry["action"]:
                    sessions[entry["user_id"]] = entry["timestamp"]
                elif "logged out" in entry["action"] and entry["user_id"] in sessions:
                    sessions.pop(entry["user_id"])
            elif entry["endpoint"] is not None and entry["duration_ms"] is not None:
                api_calls_raw.setdefault(entry["endpoint"], []).append(entry["duration_ms"])
    return error_summary, api_calls_raw, sessions

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Establishes and returns a database connection.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    print(f"Connecting to DB at {db_path} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    return conn

def setup_database(conn: sqlite3.Connection) -> None:
    """
    Sets up the necessary tables in the database.

    Args:
        conn: The database connection object.
    """
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()

def insert_error_summary(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """
    Inserts error summary data into the database using parameterized queries.

    Args:
        conn: The database connection object.
        error_summary: A dictionary mapping error messages to their counts.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                  (current_time, msg, count))
    conn.commit()

def insert_api_metrics(conn: sqlite3.Connection, api_calls_raw: Dict[str, List[int]]) -> None:
    """
    Calculates average API latency and inserts metrics into the database using parameterized queries.

    Args:
        conn: The database connection object.
        api_calls_raw: A dictionary mapping API endpoints to a list of their durations.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ep, times in api_calls_raw.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                  (current_time, ep, avg))
    conn.commit()

def generate_html_report(
    error_summary: Dict[str, int],
    api_calls_raw: Dict[str, List[int]],
    active_sessions_count: int,
) -> str:
    """
    Generates an HTML report from processed log data.

    Args:
        error_summary: A dictionary mapping error messages to their counts.
        api_calls_raw: A dictionary mapping API endpoints to a list of their durations.
        active_sessions_count: The number of active user sessions.

    Returns:
        A string containing the HTML report content.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_calls_raw.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

def write_report_file(content: str, path: str) -> None:
    """
    Writes the generated report content to a specified file.

    Args:
        content: The content of the report.
        path: The path where the report file should be written.
    """
    with open(path, "w") as f:
        f.write(content)
    print(f"Report generated at {path}")

def main():
    """
    Main function to orchestrate log processing, database updates, and report generation.
    """
    # Extract
    log_entries = read_log_file(LOG_FILE)
    print(f"Processed {len(log_entries)} log entries.")

    # Transform
    error_summary, api_calls_raw, sessions = process_log_entries(log_entries)
    active_sessions_count = len(sessions)

    # Load
    conn = get_db_connection(DB_PATH)
    setup_database(conn)
    insert_error_summary(conn, error_summary)
    insert_api_metrics(conn, api_calls_raw)
    conn.close()

    # Report Generation
    html_report_content = generate_html_report(error_summary, api_calls_raw, active_sessions_count)
    write_report_file("report.html", html_report_content)

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