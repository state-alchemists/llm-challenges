import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

# --- Configuration ---
@dataclass
class Config:
    db_path: str
    log_file_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> 'Config':
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file_path=os.getenv("LOG_FILE_PATH", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123")
        )

# --- Data Models ---
@dataclass
class LogEntry:
    timestamp: datetime.datetime
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None

@dataclass
class ErrorSummary:
    message: str
    count: int

@dataclass
class ApiLatency:
    endpoint: str
    avg_ms: float

# --- Extraction ---
def parse_log_line(line: str) -> Optional[LogEntry]:
    """
    Parses a single log line using regex and returns a LogEntry object.
    Supports INFO, ERROR, WARN levels, user login/logout, and API calls.
    """
    # General log line pattern
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)", line)
    if not match:
        return None

    dt_str, level, message = match.groups()
    timestamp = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None

    if level == "INFO":
        if "User" in message:
            user_match = re.search(r"User (\w+) (.*)", message)
            if user_match:
                user_id, action = user_match.groups()
        elif "API" in message:
            api_match = re.search(r"API (\S+) took (\d+)ms", message)
            if api_match:
                endpoint, duration_ms_str = api_match.groups()
                duration_ms = int(duration_ms_str)
    
    return LogEntry(
        timestamp=timestamp,
        level=level,
        message=message,
        user_id=user_id,
        action=action,
        endpoint=endpoint,
        duration_ms=duration_ms
    )

def extract_log_data(log_file_path: str) -> List[LogEntry]:
    """
    Reads the log file, parses each line, and returns a list of LogEntry objects.
    """
    log_entries: List[LogEntry] = []
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                entry = parse_log_line(line.strip())
                if entry:
                    log_entries.append(entry)
    return log_entries

# --- Transformation ---
def process_log_entries(
    log_entries: List[LogEntry]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes a list of LogEntry objects to extract error summaries,
    raw API call latencies, and active session count.
    Returns (error_counts, api_calls_raw, active_sessions_count).
    """
    error_counts: Dict[str, int] = {}
    api_calls_raw: Dict[str, List[int]] = {}
    sessions: Dict[str, datetime.datetime] = {}

    for entry in log_entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.level == "INFO" and entry.user_id and entry.action:
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)
        elif entry.level == "INFO" and entry.endpoint and entry.duration_ms is not None:
            api_calls_raw.setdefault(entry.endpoint, []).append(entry.duration_ms)
    
    active_sessions_count = len(sessions)
    return error_counts, api_calls_raw, active_sessions_count

def calculate_api_averages(api_calls_raw: Dict[str, List[int]]) -> List[ApiLatency]:
    """
    Calculates average API latencies from raw API call data.
    """
    api_latencies: List[ApiLatency] = []
    for ep, times in api_calls_raw.items():
        if times:
            avg = sum(times) / len(times)
            api_latencies.append(ApiLatency(endpoint=ep, avg_ms=avg))
    return api_latencies

# --- Loading ---
class DatabaseManager:
    """
    Manages database connection and operations for metrics.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def create_tables(self) -> None:
        """
        Creates necessary tables in the database if they don't exist.
        """
        if self.cursor:
            self.cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
            self.cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        else:
            raise RuntimeError("Database cursor not initialized.")

    def insert_errors(self, dt: datetime.datetime, message: str, count: int) -> None:
        """
        Inserts error summary into the 'errors' table using parameterized query.
        """
        if self.cursor:
            self.cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (dt.isoformat(), message, count)
            )
        else:
            raise RuntimeError("Database cursor not initialized.")

    def insert_api_metrics(self, dt: datetime.datetime, endpoint: str, avg_ms: float) -> None:
        """
        Inserts API metrics into the 'api_metrics' table using parameterized query.
        """
        if self.cursor:
            self.cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (dt.isoformat(), endpoint, avg_ms)
            )
        else:
            raise RuntimeError("Database cursor not initialized.")

def generate_report_html(
    error_summary_dict: Dict[str, int],
    api_latencies: List[ApiLatency],
    active_sessions_count: int
) -> str:
    """
    Generates the HTML content for the system report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary_dict.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for api_latency in api_latencies:
        out += f"<tr><td>{api_latency.endpoint}</td><td>{round(api_latency.avg_ms, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

def write_report_file(html_content: str, output_path: str) -> None:
    """
    Writes the given HTML content to the specified output file.
    """
    with open(output_path, "w") as f:
        f.write(html_content)

# --- Main Logic ---
def main() -> None:
    """
    Main function to orchestrate the log processing and report generation.
    """
    config = Config.from_env()

    # Create dummy log file if it doesn't exist for demonstration
    if not os.path.exists(config.log_file_path):
        print(f"Creating dummy log file: {config.log_file_path}")
        with open(config.log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO User 101 logged in\n")
            f.write("2024-01-01 12:20:00 INFO API /data/items took 120ms\n")


    print(f"Processing logs from {config.log_file_path}...")
    log_entries = extract_log_data(config.log_file_path)

    error_counts, api_calls_raw, active_sessions_count = process_log_entries(log_entries)
    api_latencies = calculate_api_averages(api_calls_raw)

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    with DatabaseManager(config.db_path) as db_manager:
        db_manager.create_tables()
        current_dt = datetime.datetime.now()
        
        for msg, count in error_counts.items():
            db_manager.insert_errors(current_dt, msg, count)
        
        for api_latency in api_latencies:
            db_manager.insert_api_metrics(current_dt, api_latency.endpoint, api_latency.avg_ms)

    html_report = generate_report_html(error_counts, api_latencies, active_sessions_count)
    report_output_path = "report.html"
    write_report_file(html_report, report_output_path)

    print(f"Report generated at {report_output_path}")
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
