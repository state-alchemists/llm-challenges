import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Optional, Tuple

# --- Configuration (Requirement 1: Environment variables) ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
REPORT_HTML_FILE = os.getenv("REPORT_HTML_FILE", "report.html")

# Regex patterns (Requirement 4: Use regex for log parsing)
LOG_LINE_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) (?P<message>.*)$"
)
USER_ACTION_PATTERN = re.compile(r"User (?P<user_id>\d+) (?P<action>.*)$")
API_CALL_PATTERN = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$")


def read_log_file(log_file_path: str) -> List[str]:
    """
    Reads a log file and returns its content as a list of lines.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of strings, where each string is a line from the log file.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return []
    with open(log_file_path, "r") as f:
        return f.readlines()


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex and extracts relevant information.

    Args:
        line: The log line to parse.

    Returns:
        A dictionary containing parsed data (timestamp, level, message,
        and specific details for USER and API events), or None if the line
        does not match the expected pattern.
    """
    match = LOG_LINE_PATTERN.match(line)
    if not match:
        return None

    data = match.groupdict()
    # Combine date and time for a full timestamp
    data["timestamp"] = f"{data['date']} {data['time']}"

    if data["level"] == "INFO":
        user_match = USER_ACTION_PATTERN.match(data["message"])
        if user_match:
            user_data = user_match.groupdict()
            data["type"] = "USR"
            data["user_id"] = user_data["user_id"]
            data["action"] = user_data["action"]
            return data

        api_match = API_CALL_PATTERN.match(data["message"])
        if api_match:
            api_data = api_match.groupdict()
            data["type"] = "API"
            data["endpoint"] = api_data["endpoint"]
            data["duration_ms"] = int(api_data["duration"])
            return data
    elif data["level"] == "ERROR":
        data["type"] = "ERR"
        data["message_detail"] = data["message"]
        return data
    elif data["level"] == "WARN":
        data["type"] = "WARN"
        data["message_detail"] = data["message"]
        return data
    return None


def process_log_entries(
    log_lines: List[str],
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """
    Processes a list of raw log lines, extracts information, and aggregates
    error summaries, API latency data, and active user sessions.

    Args:
        log_lines: A list of raw log strings.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - api_latency_data: A dictionary mapping API endpoints to a list of their latencies in ms.
        - active_sessions: A dictionary mapping user IDs to their login timestamps.
    """
    error_summary: Dict[str, int] = {}
    api_latency_data: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}
    
    for line in log_lines:
        parsed_data = parse_log_line(line)
        if not parsed_data:
            continue

        entry_type = parsed_data.get("type")
        if entry_type == "ERR":
            msg = parsed_data["message_detail"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif entry_type == "USR":
            uid = parsed_data["user_id"]
            action = parsed_data["action"]
            timestamp = parsed_data["timestamp"]
            if "logged in" in action:
                active_sessions[uid] = timestamp
            elif "logged out" in action and uid in active_sessions:
                active_sessions.pop(uid)
        elif entry_type == "API":
            endpoint = parsed_data["endpoint"]
            duration = parsed_data["duration_ms"]
            api_latency_data.setdefault(endpoint, []).append(duration)
    
    return error_summary, api_latency_data, active_sessions


def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Connects to the SQLite database and creates the necessary tables if they don't exist.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
        """
    )
    conn.commit()
    return conn


def insert_error_metrics(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """
    Inserts aggregated error metrics into the database.

    Args:
        conn: The database connection object.
        error_summary: A dictionary mapping error messages to their counts.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().isoformat()
    for msg, count in error_summary.items():
        # Requirement 2: Parameterized query to prevent SQL injection
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (current_time, msg, count),
        )
    conn.commit()


def insert_api_metrics(
    conn: sqlite3.Connection, api_latency_data: Dict[str, List[int]]
) -> None:
    """
    Calculates average API latencies and inserts them into the database.

    Args:
        conn: The database connection object.
        api_latency_data: A dictionary mapping API endpoints to a list of their latencies in ms.
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().isoformat()
    for ep, times in api_latency_data.items():
        if times:
            avg = sum(times) / len(times)
            # Requirement 2: Parameterized query to prevent SQL injection
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (current_time, ep, avg),
            )
    conn.commit()


def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_data: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str,
) -> None:
    """
    Generates an HTML report summarizing error counts, API latencies, and active sessions.

    Args:
        error_summary: A dictionary mapping error messages to their counts.
        api_latency_data: A dictionary mapping API endpoints to a list of their latencies in ms.
        active_sessions_count: The total number of active user sessions.
        output_file: The path where the HTML report will be saved.
    """
    report_content = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        report_content += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    report_content += """</ul>

<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in api_latency_data.items():
        if times:
            avg = sum(times) / len(times)
            report_content += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    report_content += f"""</table>

<h2>Active Sessions</h2>
<p>{active_sessions_count} user(s) currently active</p>
</body>
</html>
"""

    with open(output_file, "w") as f:
        f.write(report_content)
    print(f"Report generated at {output_file}")


def main() -> None:
    """
    Main function to orchestrate the log processing and report generation.
    """
    print("Starting log processing job...")

    # --- Extract ---
    log_lines = read_log_file(LOG_FILE)
    if not log_lines:
        print("No log lines to process. Exiting.")
        return

    # --- Transform ---
    error_summary, api_latency_data, active_sessions = process_log_entries(log_lines)
    active_sessions_count = len(active_sessions)

    # --- Load ---
    conn = initialize_database(DB_PATH)
    try:
        insert_error_metrics(conn, error_summary)
        insert_api_metrics(conn, api_latency_data)
    finally:
        conn.close()

    generate_report_html(
        error_summary, api_latency_data, active_sessions_count, REPORT_HTML_FILE
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /data/items took 120ms\n")
            f.write("2024-01-01 12:16:00 INFO API /data/items took 80ms\n")
    main()
