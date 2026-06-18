import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# --- Configuration ---
DB_PATH = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE = os.getenv("PIPELINE_LOG_FILE", "server.log")
DB_HOST = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS = os.getenv("PIPELINE_DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

@dataclass
class ProcessedData:
    errors: Dict[str, int] = field(default_factory=dict)
    api_metrics: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: Dict[str, str] = field(default_factory=dict)

def parse_logs(file_path: str) -> Tuple[List[LogEntry], Dict[str, str]]:
    """
    Parses server logs using regex to extract structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A tuple containing a list of all parsed LogEntries and a map of active sessions.
    """
    entries = []
    sessions = {}
    
    # Regex patterns for different log types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (logged in|logged out)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries, sessions

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = base_pattern.match(line)
            if not match:
                continue
                
            dt, lvl, msg = match.groups()
            entry = LogEntry(timestamp=dt, level=lvl, message=msg)

            if lvl == "ERROR":
                pass # Message is already captured in LogEntry.message
            elif lvl == "INFO":
                # Check for User activity
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    entry.user_id = uid
                    entry.action = action
                    if action == "logged in":
                        sessions[uid] = dt
                    elif action == "logged out":
                        sessions.pop(uid, None)
                
                # Check for API calls
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint, latency = api_match.groups()
                    entry.endpoint = endpoint
                    entry.latency_ms = int(latency)
            elif lvl == "WARN":
                pass # Message captured

            entries.append(entry)
            
    return entries, sessions

def transform_data(entries: List[LogEntry]) -> ProcessedData:
    """
    Transforms raw log entries into aggregated metrics for the report.
    
    Args:
        entries: List of parsed LogEntry objects.
        
    Returns:
        ProcessedData containing error counts and API latency lists.
    """
    data = ProcessedData()
    
    for entry in entries:
        if entry.level == "ERROR":
            data.errors[entry.message] = data.errors.get(entry.message, 0) + 1
        
        if entry.endpoint and entry.latency_ms is not None:
            data.api_metrics.setdefault(entry.endpoint, []).append(entry.latency_ms)
            
    return data

def load_to_db(data: ProcessedData) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        data: The processed metrics to load.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized inserts for errors
        for msg, count in data.errors.items():
            c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))

        # Parameterized inserts for API metrics
        for ep, times in data.api_metrics.items():
            avg = sum(times) / len(times) if times else 0
            c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(data: ProcessedData, active_sessions: Dict[str, str]) -> None:
    """
    Generates the final HTML report based on processed data.
    
    Args:
        data: Aggregated metrics.
        active_sessions: Current map of active users.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in data.errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in data.api_metrics.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Orchestrates the Extract, Transform, Load, and Report process.
    """
    # Extract
    entries, active_sessions = parse_logs(LOG_FILE)
    
    # Transform
    data = transform_data(entries)
    
    # Load
    load_to_db(data)
    
    # Report
    generate_report(data, active_sessions)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure log file exists for the demo (maintaining original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
