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

def parse_logs(file_path: str) -> Tuple[List[LogEntry], Dict[str, str]]:
    """
    Parses the server log file using regex to extract errors, user actions, and API metrics.
    
    Returns a tuple of (all_entries, active_sessions).
    """
    entries: List[LogEntry] = []
    sessions: Dict[str, str] = {}
    
    # Regex patterns
    # General format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\d+) (.*)$")
    api_pattern = re.compile(r"API ([^\s]+) took (\d+)ms")

    if not os.path.exists(file_path):
        return [], {}

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = base_pattern.match(line)
            if not match:
                continue
                
            dt, lvl, msg = match.groups()
            
            if lvl == "ERROR":
                entries.append(LogEntry(timestamp=dt, level=lvl, message=msg))
            
            elif lvl == "WARN":
                entries.append(LogEntry(timestamp=dt, level=lvl, message=msg))
                
            elif lvl == "INFO":
                # User activity
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action:
                        sessions.pop(uid, None)
                    entries.append(LogEntry(timestamp=dt, level=lvl, message=msg, user_id=uid, action=action))
                    continue
                
                # API metrics
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint, latency = api_match.groups()
                    entries.append(LogEntry(
                        timestamp=dt, 
                        level=lvl, 
                        message=msg, 
                        endpoint=endpoint, 
                        latency_ms=int(latency)
                    ))

    return entries, sessions

def load_metrics(entries: List[LogEntry]) -> None:
    """
    Processes log entries and loads aggregated metrics into the SQLite database.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Error aggregation
        error_counts: Dict[str, int] = {}
        for e in entries:
            if e.level == "ERROR":
                error_counts[e.message] = error_counts.get(e.message, 0) + 1

        now = datetime.datetime.now().isoformat()
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        # API aggregation
        endpoint_stats: Dict[str, List[int]] = {}
        for e in entries:
            if e.endpoint and e.latency_ms is not None:
                endpoint_stats.setdefault(e.endpoint, []).append(e.latency_ms)

        for ep, times in endpoint_stats.items():
            avg = sum(times) / len(times)
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()
    finally:
        conn.close()

def generate_report(entries: List[LogEntry], sessions: Dict[str, str], output_path: str) -> None:
    """
    Generates the HTML report based on parsed log data.
    """
    # Aggregate errors for the report
    error_counts: Dict[str, int] = {}
    for e in entries:
        if e.level == "ERROR":
            error_counts[e.message] = error_counts.get(e.message, 0) + 1

    # Aggregate API latency for the report
    endpoint_stats: Dict[str, List[int]] = {}
    for e in entries:
        if e.endpoint and e.latency_ms is not None:
            endpoint_stats.setdefault(e.endpoint, []).append(e.latency_ms)

    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    # Error Summary
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        html += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    # API Latency Table
    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    # Active Sessions
    html += f"<h2>Active Sessions</h2>\n<p>{len(sessions)} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open(output_path, "w") as f:
        f.write(html)

def run_pipeline() -> None:
    """
    Main pipeline execution flow: Extract -> Transform -> Load.
    """
    # Extract
    entries, sessions = parse_logs(LOG_FILE)
    
    # Load (Database)
    load_metrics(entries)
    
    # Transform/Load (Report)
    generate_report(entries, sessions, "report.html")
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Seed file for demonstration if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
