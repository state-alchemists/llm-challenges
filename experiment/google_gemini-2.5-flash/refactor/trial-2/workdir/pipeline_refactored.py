import datetime
import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

# --- Configuration (loaded from environment variables) ---
def get_config() -> Dict[str, str]:
    """
    Loads configuration from environment variables.
    """
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"), # This is still here for completeness but not used for sqlite3
    }

# --- Extract Stage ---
def load_log_data(log_file_path: str) -> List[str]:
    """
    Reads log lines from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of log file lines.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return []
    with open(log_file_path, "r") as f:
        return f.readlines()

def connect_db(db_path: str) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    print(f"Connecting to SQLite database: {db_path}...")
    return sqlite3.connect(db_path)

# --- Transform Stage ---
def parse_log_line(line: str) -> Optional[Dict]:
    """
    Parses a single log line using regex to extract relevant information.

    Args:
        line: A single log line string.

    Returns:
        A dictionary containing parsed log data, or None if the line cannot be parsed.
    """
    # Regex to capture timestamp, level, and the rest of the message
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$", line)
    if not match:
        return None

    timestamp_str, level, message = match.groups()
    parsed_data = {"timestamp": timestamp_str, "level": level, "message": message.strip()}

    if level == "INFO":
        user_login_match = re.search(r"User (\d+) (logged in|logged out)", message)
        if user_login_match:
            parsed_data["type"] = "USER_EVENT"
            parsed_data["user_id"] = user_login_match.group(1)
            parsed_data["action"] = user_login_match.group(2)
            return parsed_data

        api_call_match = re.search(r"API (/[\w/]+) took (\d+)ms", message)
        if api_call_match:
            parsed_data["type"] = "API_CALL"
            parsed_data["endpoint"] = api_call_match.group(1)
            parsed_data["duration_ms"] = int(api_call_match.group(2))
            return parsed_data
    elif level == "ERROR":
        parsed_data["type"] = "ERROR"
        return parsed_data
    elif level == "WARN":
        parsed_data["type"] = "WARN"
        return parsed_data

    return None

def process_log_entries(log_lines: List[str]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes a list of raw log lines, parsing them and aggregating data
    for error summaries, API call statistics, and active sessions.

    Args:
        log_lines: A list of raw log line strings.

    Returns:
        A tuple containing:
        - error_summary (Dict[str, int]): Counts of each unique error message.
        - api_latency_stats (Dict[str, List[int]]): List of latencies for each API endpoint.
        - active_sessions_count (int): Current count of active user sessions.
    """
    error_summary: Dict[str, int] = {}
    api_calls_raw: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {} # user_id -> login_timestamp

    for line in log_lines:
        parsed_data = parse_log_line(line)
        if not parsed_data:
            continue

        if parsed_data.get("type") == "ERROR":
            msg = parsed_data["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif parsed_data.get("type") == "USER_EVENT":
            user_id = parsed_data["user_id"]
            action = parsed_data["action"]
            if "logged in" in action:
                sessions[user_id] = parsed_data["timestamp"]
            elif "logged out" in action and user_id in sessions:
                sessions.pop(user_id)
        elif parsed_data.get("type") == "API_CALL":
            endpoint = parsed_data["endpoint"]
            duration = parsed_data["duration_ms"]
            api_calls_raw.setdefault(endpoint, []).append(duration)
    
    return error_summary, api_calls_raw, len(sessions)

# --- Load Stage ---
def setup_database(conn: sqlite3.Connection) -> None:
    """
    Sets up the necessary tables in the SQLite database.

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
        error_summary: A dictionary of error messages and their counts.
    """
    c = conn.cursor()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )
    conn.commit()

def insert_api_metrics(conn: sqlite3.Connection, api_latency_stats: Dict[str, List[int]]) -> None:
    """
    Inserts API latency metrics into the database using parameterized queries.

    Args:
        conn: The database connection object.
        api_latency_stats: A dictionary where keys are API endpoints and values
                           are lists of latency measurements in milliseconds.
    """
    c = conn.cursor()
    for ep, times in api_latency_stats.items():
        if times:
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), ep, avg)
            )
    conn.commit()

def generate_report(
    error_summary: Dict[str, int],
    api_latency_stats_raw: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: Counts of each unique error message.
        api_latency_stats_raw: Raw API latency data (endpoint to list of durations).
        active_sessions_count: The count of currently active user sessions.
        output_file: The path where the HTML report will be saved.
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
    for ep, times in api_latency_stats_raw.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += """</table>

<h2>Active Sessions</h2>
"""
    out += f"<p>{active_sessions_count} user(s) currently active</p>\\n"
    out += """</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated at {output_file}")


# --- Main Orchestration ---
def main():
    """
    Orchestrates the log processing, database interaction, and report generation.
    """
    config = get_config()
    log_file_path = config["LOG_FILE"]
    db_path = config["DB_PATH"]
    report_file_path = config["REPORT_FILE"]

    # Extract
    log_lines = load_log_data(log_file_path)
    if not log_lines:
        return

    # Transform
    error_summary, api_latency_stats_raw, active_sessions_count = process_log_entries(log_lines)

    # Load
    conn = None
    try:
        conn = connect_db(db_path)
        setup_database(conn)
        insert_error_summary(conn, error_summary)
        insert_api_metrics(conn, api_latency_stats_raw)
        generate_report(error_summary, api_latency_stats_raw, active_sessions_count, report_file_path)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # This block is for initial setup if the log file doesn't exist,
    # to make the script runnable out-of-the-box.
    # In a real scenario, the log file would be generated by the server.
    config = get_config()
    log_file = config["LOG_FILE"]
    # Ensure the log file is always fresh for demonstration purposes
    if os.path.exists(log_file):
        os.remove(log_file)
    
    print(f"Creating a sample log file at {log_file} for demonstration.")
    with open(log_file, "w") as f:
        f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        f.write("2024-01-01 12:05:05 ERROR Another Database timeout\n")
        f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        f.write("2024-01-01 12:10:00 INFO API /data/stats took 120ms\n")
        f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
        f.write("2024-01-01 12:11:00 ERROR File not found\n")
    main()
