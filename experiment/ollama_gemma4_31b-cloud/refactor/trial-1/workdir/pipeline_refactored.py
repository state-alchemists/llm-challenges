import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

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
    latency: Optional[int] = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regular expressions.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    # Regex patterns for different log levels and types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (.*)$")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            timestamp, level, content = match.groups()
            
            if level == "ERROR" or level == "WARN":
                entries.append(LogEntry(timestamp, level, content))
            
            elif level == "INFO":
                # Check if it's a User log
                user_match = user_pattern.match(content)
                if user_match:
                    uid, action = user_match.groups()
                    entries.append(LogEntry(timestamp, level, content, user_id=uid, action=action))
                    continue
                
                # Check if it's an API log
                api_match = api_pattern.search(content)
                if api_match:
                    endpoint, latency = api_match.groups()
                    entries.append(LogEntry(timestamp, level, content, endpoint=endpoint, latency=int(latency)))
    
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Aggregates raw log entries into summaries for the report and DB.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A tuple containing:
        - error_summary: Map of error message to occurrence count.
        - api_stats: Map of endpoint to list of latencies.
        - active_sessions: Count of currently active users.
    """
    error_summary = {}
    api_stats = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1
        
        elif entry.level == "INFO" and entry.user_id:
            if entry.action and "logged in" in entry.action:
                sessions.add(entry.user_id)
            elif entry.action and "logged out" in entry.action:
                sessions.discard(entry.user_id)
        
        elif entry.level == "INFO" and entry.endpoint:
            api_stats.setdefault(entry.endpoint, []).append(entry.latency or 0)

    return error_summary, api_stats, len(sessions)

def load_to_db(error_summary: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_summary: Map of error message to occurrence count.
        api_stats: Map of endpoint to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load errors
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Load API metrics
        api_data = []
        for ep, latencies in api_stats.items():
            avg = sum(latencies) / len(latencies) if latencies else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_summary: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report file.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_summary.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"
    
    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, latencies in api_stats.items():
        avg = sum(latencies) / len(latencies) if latencies else 0
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"
    
    html += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    html += "</body>\n</html>"
    
    with open("report.html", "w") as f:
        f.write(html)

def run_pipeline() -> None:
    """
    Main execution flow: Extract -> Transform -> Load.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_summary, api_stats, session_count = transform_logs(entries)
    
    # Load (DB & Report)
    load_to_db(error_summary, api_stats)
    generate_report(error_summary, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Preserve the mock data generation from the original script for testability
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
