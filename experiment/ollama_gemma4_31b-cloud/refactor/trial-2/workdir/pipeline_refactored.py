import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, TypedDict, Optional

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

class LogEntry(TypedDict):
    timestamp: str
    level: str
    message: str
    user_id: Optional[str]
    action: Optional[str]
    endpoint: Optional[str]
    latency: Optional[int]

def parse_logs(file_path: str) -> Tuple[List[LogEntry], Dict[str, str], List[Dict]]:
    """
    Extracts and parses data from the server log file.
    
    Returns:
        A tuple containing:
        - entries: A list of parsed log entries.
        - active_sessions: A mapping of user IDs to their last login timestamp.
        - api_calls: A list of API call metrics (endpoint and latency).
    """
    entries: List[LogEntry] = []
    active_sessions: Dict[str, str] = {}
    api_calls: List[Dict] = []

    # Regex patterns for different log types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
    user_pattern = re.compile(r"User (\w+) (logged in|logged out)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries, active_sessions, api_calls

    with open(file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if not match:
                continue

            timestamp, level, message = match.groups()
            entry: LogEntry = {"timestamp": timestamp, "level": level, "message": message, 
                               "user_id": None, "action": None, "endpoint": None, "latency": None}

            if level == "ERROR":
                entries.append(entry)
            
            elif level == "INFO":
                # Check for User activity
                user_match = user_pattern.search(message)
                if user_match:
                    uid, action = user_match.groups()
                    entry["user_id"] = uid
                    entry["action"] = action
                    if action == "logged in":
                        active_sessions[uid] = timestamp
                    elif action == "logged out":
                        active_sessions.pop(uid, None)
                    entries.append(entry)
                else:
                    # Check for API activity
                    api_match = api_pattern.search(message)
                    if api_match:
                        endpoint, latency = api_match.groups()
                        entry["endpoint"] = endpoint
                        entry["latency"] = int(latency)
                        api_calls.append({"timestamp": timestamp, "endpoint": endpoint, "ms": int(latency)})
            
            elif level == "WARN":
                entries.append(entry)

    return entries, active_sessions, api_calls

def transform_metrics(entries: List[LogEntry], api_calls: List[Dict]) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms raw log data into aggregated metrics.
    
    Returns:
        A tuple containing:
        - error_counts: Map of error messages to their frequency.
        - endpoint_latencies: Map of endpoints to a list of their recorded latencies.
    """
    error_counts: Dict[str, int] = {}
    endpoint_latencies: Dict[str, List[int]] = {}

    for entry in entries:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for call in api_calls:
        ep = call["endpoint"]
        endpoint_latencies.setdefault(ep, []).append(call["ms"])

    return error_counts, endpoint_latencies

def load_to_db(error_counts: Dict[str, int], endpoint_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics into the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in endpoint_latencies.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], endpoint_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates an HTML report summarizing the system state.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_counts.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times) if times else 0
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    html += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(html)

def run_pipeline() -> None:
    """
    Main execution flow: Extract -> Transform -> Load -> Report.
    """
    # Extract
    entries, sessions, api_calls = parse_logs(LOG_FILE)
    
    # Transform
    error_counts, endpoint_latencies = transform_metrics(entries, api_calls)
    
    # Load
    load_to_db(error_counts, endpoint_latencies)
    
    # Report
    generate_report(error_counts, endpoint_latencies, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure a log file exists for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
