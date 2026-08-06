import datetime
import os
import re
import sqlite3
from typing import Dict, Iterator, List, Any, Optional, Tuple, TypedDict

# Define a TypedDict for configuration settings
class Config(TypedDict):
    db_path: str
    log_file_path: str
    report_output_path: str

# 1. Use environment variables for all config
def load_config() -> Config:
    """Loads configuration from environment variables with default values."""
    return Config(
        db_path=os.getenv("METRICS_DB_PATH", "metrics.db"),
        log_file_path=os.getenv("SERVER_LOG_FILE", "server.log"),
        report_output_path=os.getenv("REPORT_OUTPUT_PATH", "report.html")
    )

def init_db(db_path: str) -> sqlite3.Connection:
    """
    Initializes the SQLite database, creating tables if they don't exist.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn

# 3. Break it into well-named functions following Extract -> Transform -> Load
# 4. Use regex for log line parsing

def extract_log_lines(log_file_path: str) -> Iterator[str]:
    """
    Extracts log lines from the specified log file.
    Yields each line for processing.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return
    with open(log_file_path, "r") as f:
        for line in f:
            yield line.strip()

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regular expressions.
    Returns a dictionary of extracted data or None if parsing fails.
    """
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)")
    match = log_pattern.match(line)
    if not match:
        return None

    dt_str, level, message = match.groups()
    parsed_data = {"datetime": dt_str, "level": level, "message": message}

    if level == "INFO":
        user_login_logout_pattern = re.compile(r"User (\d+) (logged in|logged out)")
        api_call_pattern = re.compile(r"API (/[\w/]+) took (\d+)ms")

        user_match = user_login_logout_pattern.search(message)
        if user_match:
            parsed_data["type"] = "user_event"
            parsed_data["user_id"] = user_match.group(1)
            parsed_data["action"] = user_match.group(2)
        else:
            api_match = api_call_pattern.search(message)
            if api_match:
                parsed_data["type"] = "api_call"
                parsed_data["endpoint"] = api_match.group(1)
                parsed_data["latency_ms"] = int(api_match.group(2))
            else:
                parsed_data["type"] = "info" # Generic INFO message
    elif level == "ERROR":
        parsed_data["type"] = "error"
    elif level == "WARN":
        parsed_data["type"] = "warning"

    return parsed_data

def transform_log_data(log_lines_iterator: Iterator[str]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Transforms raw log lines into aggregated metrics: error summary, API latencies,
    and active session count.
    """
    error_summary: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {} # user_id -> login_datetime

    for line in log_lines_iterator:
        parsed = parse_log_line(line)
        if not parsed:
            continue

        if parsed["type"] == "error":
            msg = parsed["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif parsed["type"] == "user_event":
            user_id = parsed["user_id"]
            action = parsed["action"]
            if action == "logged in":
                active_sessions[user_id] = parsed["datetime"]
            elif action == "logged out" and user_id in active_sessions:
                active_sessions.pop(user_id)
        elif parsed["type"] == "api_call":
            endpoint = parsed["endpoint"]
            latency = parsed["latency_ms"]
            api_latencies.setdefault(endpoint, []).append(latency)
    return error_summary, api_latencies, len(active_sessions)

def load_metrics(conn: sqlite3.Connection, error_summary: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Loads aggregated error and API latency metrics into the database.
    2. Fix the SQL injection - use parameterized queries
    """
    cursor = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (current_time, msg, count)
        )

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (current_time, ep, avg)
        )
    conn.commit()

def generate_report_html(conn: sqlite3.Connection, active_sessions_count: int) -> str:
    """
    Generates the HTML report content by querying the database and
    including the active sessions count.
    """
    cursor = conn.cursor()

    # Fetch error summary
    error_data = cursor.execute("SELECT message, count FROM errors ORDER BY count DESC").fetchall()

    # Fetch API latency
    api_data = cursor.execute("SELECT endpoint, avg_ms FROM api_metrics ORDER BY endpoint ASC").fetchall()

    out = "<html>\\n<head><title>System Report</title></head>\\n<body>\\n"
    out += "<h1>Error Summary</h1>\\n<ul>\\n"
    for err_msg, count in error_data:
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += "<h2>API Latency</h2>\\n<table border='1'>\\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\\n"
    for ep, avg in api_data:
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += "<h2>Active Sessions</h2>\\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\\n"
    out += "</body>\\n</html>"
    return out

def write_report_file(html_content: str, output_file_path: str) -> None:
    """Writes the generated HTML content to a file."""
    with open(output_file_path, "w") as f:
        f.write(html_content)
    print(f"Report generated at {output_file_path}")

def main():
    """
    Main function to orchestrate the log processing and report generation.
    """
    config = load_config()
    print(f"Using DB: {config['db_path']}, Log file: {config['log_file_path']}, Report output: {config['report_output_path']}")

    # Ensure a log file exists for demonstration if not present
    if not os.path.exists(config['log_file_path']):
        print(f"Creating a sample log file at {config['log_file_path']}")
        with open(config['log_file_path'], "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:11:00 INFO User 43 logged in\n") # Added for active session test

    conn = None
    try:
        conn = init_db(config['db_path'])
        
        log_lines = extract_log_lines(config['log_file_path'])
        error_summary, api_latencies, active_sessions_count = transform_log_data(log_lines)
        
        load_metrics(conn, error_summary, api_latencies)
        
        html_report_content = generate_report_html(conn, active_sessions_count)
        write_report_file(html_report_content, config['report_output_path'])
        
        print(f"Job finished at {datetime.datetime.now()}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
