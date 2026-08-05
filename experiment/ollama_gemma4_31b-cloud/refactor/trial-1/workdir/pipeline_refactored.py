import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

# Regex patterns for log parsing
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
USER_PATTERN = re.compile(r"User (\w+) (.*)$")
API_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Reads server logs and parses them into a list of LogEntry objects.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = LOG_PATTERN.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            entry = LogEntry(timestamp=timestamp, level=level, message=content)
            
            if level == "INFO":
                user_match = USER_PATTERN.match(content)
                if user_match:
                    user_id, action = user_match.groups()
                    entry.user_id = user_id
                    entry.action = action
                else:
                    api_match = API_PATTERN.match(content)
                    if api_match:
                        endpoint, latency = api_match.groups()
                        entry.endpoint = endpoint
                        entry.latency_ms = int(latency)
            
            entries.append(entry)
            
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries into aggregated metrics.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A tuple containing:
        - error_counts: Map of error message to occurrence count.
        - api_latencies: Map of endpoint to list of latency values.
        - active_sessions: Count of users who logged in but haven't logged out.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
            
        elif entry.level == "INFO":
            if entry.user_id:
                if "logged in" in (entry.action or ""):
                    sessions[entry.user_id] = entry.timestamp
                elif "logged out" in (entry.action or ""):
                    sessions.pop(entry.user_id, None)
            
            if entry.endpoint and entry.latency_ms is not None:
                api_latencies.setdefault(entry.endpoint, []).append(entry.latency_ms)
        
    return error_counts, api_latencies, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error message to count.
        api_latencies: Map of endpoint to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        for msg, count in error_counts.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))
            
        for endpoint, times in api_latencies.items():
            avg = sum(times) / len(times)
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, endpoint, avg))
            
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates an HTML report from the aggregated metrics.
    
    Args:
        error_counts: Map of error message to count.
        api_latencies: Map of endpoint to list of latencies.
        session_count: Number of active sessions.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_counts.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"
    
    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times)
        html += f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"
    
    html += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    html += "</body>\n</html>"
    
    with open("report.html", "w") as f:
        f.write(html)

def run_pipeline() -> None:
    """Main orchestrator for the log processing pipeline."""
    entries = extract_logs(LOG_FILE)
    error_counts, api_latencies, session_count = transform_logs(entries)
    load_to_db(error_counts, api_latencies)
    generate_report(error_counts, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup mock data for local testing if log file is missing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
