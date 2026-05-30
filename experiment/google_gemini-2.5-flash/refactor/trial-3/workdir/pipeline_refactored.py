
import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Iterator, Tuple

# --- Configuration ---
class Config:
    """Manages configuration settings from environment variables."""
    DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
    LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "admin")
    DB_PASS: str = os.getenv("DB_PASS", "password123")

# --- Log Parsing (Extract) ---
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) "
    r"(?P<message>.*)$"
)
USER_LOGIN_PATTERN = re.compile(r"User (?P<user_id>\w+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (?P<user_id>\w+) logged out")
API_CALL_PATTERN = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")

def parse_log_line(line: str) -> Dict[str, Any] | None:
    """Parses a single log line using regex and extracts relevant information."""
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    data = match.groupdict()
    level = data["level"]
    message = data["message"]
    timestamp = data["timestamp"]

    if level == "ERROR":
        return {"type": "ERR", "timestamp": timestamp, "message": message.strip()}
    elif level == "INFO":
        user_login_match = USER_LOGIN_PATTERN.match(message)
        user_logout_match = USER_LOGOUT_PATTERN.match(message)
        api_call_match = API_CALL_PATTERN.match(message)

        if user_login_match:
            user_data = user_login_match.groupdict()
            return {"type": "USR_LOGIN", "timestamp": timestamp, "user_id": user_data["user_id"]}
        elif user_logout_match:
            user_data = user_logout_match.groupdict()
            return {"type": "USR_LOGOUT", "timestamp": timestamp, "user_id": user_data["user_id"]}
        elif api_call_match:
            api_data = api_call_match.groupdict()
            return {"type": "API", "timestamp": timestamp, "endpoint": api_data["endpoint"], "duration_ms": int(api_data["duration"])}
        else:
            return {"type": "INFO", "timestamp": timestamp, "message": message.strip()}
    elif level == "WARN":
        return {"type": "WARN", "timestamp": timestamp, "message": message.strip()}
    return None

def read_log_file(log_file_path: str) -> Iterator[Dict[str, Any]]:
    """Reads a log file line by line and yields parsed log entries."""
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return

    with open(log_file_path, "r") as f:
        for line in f:
            parsed_line = parse_log_line(line)
            if parsed_line:
                yield parsed_line

# --- Data Transformation (Transform) ---
def analyze_errors(parsed_logs: Iterator[Dict[str, Any]]) -> Dict[str, int]:
    """Analyzes parsed logs to count occurrences of each error message."""
    error_summary: Dict[str, int] = {}
    for log_entry in parsed_logs:
        if log_entry["type"] == "ERR":
            msg = log_entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def analyze_api_latency(parsed_logs: Iterator[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Analyzes parsed logs to collect API call latencies per endpoint."""
    api_calls: Dict[str, List[int]] = {}
    for log_entry in parsed_logs:
        if log_entry["type"] == "API":
            endpoint = log_entry["endpoint"]
            duration = log_entry["duration_ms"]
            api_calls.setdefault(endpoint, []).append(duration)
    return api_calls

def track_sessions(parsed_logs: Iterator[Dict[str, Any]]) -> Dict[str, str]:
    """Tracks active user sessions based on login/logout events."""
    active_sessions: Dict[str, str] = {}
    for log_entry in parsed_logs:
        if log_entry["type"] == "USR_LOGIN":
            active_sessions[log_entry["user_id"]] = log_entry["timestamp"]
        elif log_entry["type"] == "USR_LOGOUT":
            active_sessions.pop(log_entry["user_id"], None)
    return active_sessions

# --- Database Operations (Load) ---
class DatabaseManager:
    """Manages database connection and operations."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self.cursor: sqlite3.Cursor | None = None

    def connect(self) -> None:
        """Establishes a connection to the SQLite database."""
        print(f"Connecting to database at {self.db_path}...")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def initialize_db(self) -> None:
        """Creates necessary tables if they don't exist."""
        if not self.cursor:
            raise RuntimeError("Database cursor not initialized. Call connect() first.")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        self.conn.commit()

    def insert_errors(self, error_summary: Dict[str, int]) -> None:
        """Inserts error summary data into the database using parameterized queries."""
        if not self.cursor:
            raise RuntimeError("Database cursor not initialized. Call connect() first.")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for msg, count in error_summary.items():
            self.cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (current_time, msg, count)
            )
        self.conn.commit()

    def insert_api_metrics(self, api_latencies: Dict[str, List[int]]) -> None:
        """Inserts API latency metrics into the database using parameterized queries."""
        if not self.cursor:
            raise RuntimeError("Database cursor not initialized. Call connect() first.")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for ep, times in api_latencies.items():
            if times:
                avg = sum(times) / len(times)
                self.cursor.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (current_time, ep, avg)
                )
        self.conn.commit()

    def disconnect(self) -> None:
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            print("Database connection closed.")

# --- Report Generation ---
def generate_report_html(
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    output_file: str = "report.html"
) -> None:
    """Generates an HTML report from the processed data."""
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += """<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += f"""<h2>Active Sessions</h2>
<p>{len(active_sessions)} user(s) currently active</p>
</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")

# --- Main Execution ---
def main() -> None:
    """Main function to orchestrate log processing, data analysis, and report generation."""
    config = Config()

    # Create dummy log file if it doesn't exist for demonstration
    if not os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    # Extract
    log_entries_list = list(read_log_file(config.LOG_FILE)) # Convert iterator to list for multiple passes

    # Transform
    error_summary = analyze_errors(iter(log_entries_list))
    api_latencies = analyze_api_latency(iter(log_entries_list))
    active_sessions = track_sessions(iter(log_entries_list))

    # Load (Database)
    db_manager = DatabaseManager(config.DB_PATH)
    try:
        db_manager.connect()
        db_manager.initialize_db()
        db_manager.insert_errors(error_summary)
        db_manager.insert_api_metrics(api_latencies)
    finally:
        db_manager.disconnect()

    # Generate Report
    generate_report_html(error_summary, api_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
