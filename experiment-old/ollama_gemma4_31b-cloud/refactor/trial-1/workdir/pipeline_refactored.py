import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# --- Configuration ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Data Models ---
@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class UserAction:
    timestamp: str
    user_id: str
    action: str

@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    latency_ms: int

@dataclass
class ProcessedData:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: Dict[str, str] = field(default_factory=dict)

# --- Extraction ---
def extract_logs(file_path: str) -> Tuple[List[LogEntry], List[UserAction], List[ApiCall]]:
    """
    Parses the server log file using regex to extract errors, user actions, and API calls.
    """
    errors: List[LogEntry] = []
    users: List[UserAction] = []
    api_calls: List[ApiCall] = []

    # Patterns
    # Example: 2024-01-01 12:00:00 INFO User 42 logged in
    # Example: 2024-01-01 12:05:00 ERROR Database timeout
    # Example: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    generic_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\d+) (.*)$")
    api_pattern = re.compile(r"API ([/\w\.\-]+) took (\d+)ms$")

    if not os.path.exists(file_path):
        return errors, users, api_calls

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = generic_pattern.match(line)
            if not match:
                continue

            ts, lvl, msg = match.groups()

            if lvl == "ERROR":
                errors.append(LogEntry(ts, lvl, msg))
            elif lvl == "WARN":
                errors.append(LogEntry(ts, lvl, msg)) # Keep parity with original d_list logic
            elif lvl == "INFO":
                # Check for User action
                u_match = user_pattern.search(msg)
                if u_match:
                    uid, action = u_match.groups()
                    users.append(UserAction(ts, uid, action))
                else:
                    # Check for API call
                    a_match = api_pattern.search(msg)
                    if a_match:
                        ep, lat = a_match.groups()
                        api_calls.append(ApiCall(ts, ep, int(lat)))

    return errors, users, api_calls

# --- Transformation ---
def transform_data(errors: List[LogEntry], users: List[UserAction], api_calls: List[ApiCall]) -> ProcessedData:
    """
    Aggregates raw log data into summaries for the report and database.
    """
    data = ProcessedData()

    # Error counts - focus on ERROR level for the summary as per original
    for err in errors:
        if err.level == "ERROR":
            data.error_counts[err.message] = data.error_counts.get(err.message, 0) + 1

    # Session tracking
    for user in users:
        if "logged in" in user.action:
            data.active_sessions[user.user_id] = user.timestamp
        elif "logged out" in user.action:
            data.active_sessions.pop(user.user_id, None)

    # API Latency grouping
    for call in api_calls:
        data.api_latencies.setdefault(call.endpoint, []).append(call.latency_ms)

    return data

# --- Load ---
def load_to_db(data: ProcessedData):
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Load Errors
        for msg, count in data.error_counts.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        # Load API Metrics
        for ep, times in data.api_latencies.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()

# --- Report Generation ---
def generate_report(data: ProcessedData, output_path: str = "report.html"):
    """
    Generates an HTML report with the finalized metrics.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in data.error_counts.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in data.api_latencies.items():
        avg = sum(times) / len(times) if times else 0.0
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    html += "<h2>Active Sessions</h2>\n"
    html += f"<p>{len(data.active_sessions)} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open(output_path, "w") as f:
        f.write(html)

def run_pipeline():
    """
    Main orchestration function following ETL pattern.
    """
    # Extract
    errors, users, api_calls = extract_logs(LOG_FILE)
    
    # Transform
    processed_data = transform_data(errors, users, api_calls)
    
    # Load
    load_to_db(processed_data)
    
    # Report
    generate_report(processed_data)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Bootstrapping example log for verification
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
