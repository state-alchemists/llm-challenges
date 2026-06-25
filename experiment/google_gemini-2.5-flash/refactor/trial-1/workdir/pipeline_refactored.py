import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any

# 1. Configuration: Use environment variables
def load_config() -> Dict[str, Any]:
    """Loads configuration from environment variables."""
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "5432")),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html")
    }

# 3. Extract: Log parsing using regex
def parse_log_line(line: str) -> Dict[str, Any] | None:
    """Parses a single log line using regex and returns a dictionary of its components."""
    # Regex to capture timestamp, level, and the rest of the message
    log_pattern = re.compile(
        r"^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) "
        r"(?P<level>[A-Z]+) "
        r"(?P<message>.*)$"
    )
    match = log_pattern.match(line)
    if not match:
        return None

    data = match.groupdict()
    level = data["level"]
    message = data["message"]
    parsed_entry: Dict[str, Any] = {"timestamp": data["timestamp"], "level": level}

    if level == "ERROR":
        parsed_entry["type"] = "ERR"
        parsed_entry["message"] = message.strip()
    elif level == "INFO":
        if "User" in message:
            user_match = re.search(r"User (?P<uid>\w+) (?P<action>.*)", message)
            if user_match:
                parsed_entry["type"] = "USR"
                parsed_entry["uid"] = user_match.group("uid")
                parsed_entry["action"] = user_match.group("action").strip()
        elif "API" in message:
            api_match = re.search(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms", message)
            if api_match:
                parsed_entry["type"] = "API"
                parsed_entry["endpoint"] = api_match.group("endpoint")
                parsed_entry["duration_ms"] = int(api_match.group("duration"))
            else: # API call without duration
                api_match = re.search(r"API (?P<endpoint>/\S+)", message)
                if api_match:
                    parsed_entry["type"] = "API"
                    parsed_entry["endpoint"] = api_match.group("endpoint")
                    parsed_entry["duration_ms"] = 0
        else:
            return None # Unhandled INFO message type
    elif level == "WARN":
        parsed_entry["type"] = "WARN"
        parsed_entry["message"] = message.strip()
    else:
        return None # Unhandled log level

    return parsed_entry

def read_log_file(log_file_path: str) -> List[Dict[str, Any]]:
    """Reads a log file, parses each line, and returns a list of structured log entries."""
    log_entries = []
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return log_entries

    with open(log_file_path, "r") as f:
        for line in f:
            parsed_line = parse_log_line(line)
            if parsed_line:
                log_entries.append(parsed_line)
    return log_entries

# 3. Transform: Data processing functions
def process_log_entries(
    log_entries: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Processes a list of parsed log entries to extract error summaries, API latencies, and active sessions."""
    error_summary: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in log_entries:
        entry_type = entry.get("type")
        if entry_type == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif entry_type == "API":
            endpoint = entry["endpoint"]
            duration = entry["duration_ms"]
            api_latencies.setdefault(endpoint, []).append(duration)
        elif entry_type == "USR":
            uid = entry["uid"]
            action = entry["action"]
            timestamp = entry["timestamp"]
            if "logged in" in action:
                active_sessions[uid] = timestamp
            elif "logged out" in action and uid in active_sessions:
                active_sessions.pop(uid)
    
    return error_summary, api_latencies, active_sessions

# 3. Load: Database operations
def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Establishes and returns a connection to the SQLite database."""
    print(f"Connecting to SQLite database: {db_path}") # Removed DB_HOST/PORT/USER/PASS from print for security
    return sqlite3.connect(db_path)

def initialize_db(conn: sqlite3.Connection) -> None:
    """Initializes database tables if they do not already exist."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()

def insert_error_summary(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """Inserts error summary data into the 'errors' table using parameterized queries."""
    c = conn.cursor()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )
    conn.commit()

def insert_api_metrics(conn: sqlite3.Connection, api_latencies: Dict[str, List[int]]) -> None:
    """Inserts API metrics data into the 'api_metrics' table using parameterized queries."""
    c = conn.cursor()
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )
    conn.commit()

# 3. Load: Report generation
def generate_report(
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    report_file: str
) -> None:
    """Generates an HTML report from processed log data."""
    out = "<html>\\n<head><title>System Report</title></head>\\n<body>\\n"
    out += "<h1>Error Summary</h1>\\n<ul>\\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += "<h2>API Latency</h2>\\n<table border='1'>\\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += "<h2>Active Sessions</h2>\\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\\n"
    out += "</body>\\n</html>"

    with open(report_file, "w") as f:
        f.write(out)
    print(f"Report generated: {report_file}")

def main() -> None:
    """Main function to orchestrate the log processing and reporting."""
    config = load_config()
    db_path = config["DB_PATH"]
    log_file = config["LOG_FILE"]
    report_file = config["REPORT_FILE"]

    # For demonstration, create a dummy log file if it doesn't exist
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\\n")
            f.write("2024-01-01 12:15:00 INFO API /products took 120ms\\n")
            f.write("2024-01-01 12:20:00 INFO User 100 logged in\\n")

    log_entries = read_log_file(log_file)
    error_summary, api_latencies, active_sessions = process_log_entries(log_entries)

    conn = None
    try:
        conn = get_db_connection(db_path)
        initialize_db(conn)
        insert_error_summary(conn, error_summary)
        insert_api_metrics(conn, api_latencies)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

    generate_report(error_summary, api_latencies, active_sessions, report_file)
    print("Job finished at " + str(datetime.datetime.now()))

if __name__ == "__main__":
    main()
