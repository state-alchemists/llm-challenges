import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Tuple, NamedTuple
from dataclasses import dataclass

# --- Configuration ---
# Use environment variables for all config to avoid hardcoded credentials and paths
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
# Note: DB_HOST, DB_PORT, DB_USER, DB_PASS were printed but not used for the actual sqlite3 connection.
# We include them for parity and potential future migration to a real Postgres/MySQL server.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    latency_ms: int | None = None

def parse_log_line(line: str) -> LogEntry | None:
    """
    Parses a single log line using regex.
    
    Expected formats:
    - ERROR: YYYY-MM-DD HH:MM:SS ERROR Message
    - INFO (User): YYYY-MM-DD HH:MM:SS INFO User <id> <action>
    - INFO (API): YYYY-MM-DD HH:MM:SS INFO API <endpoint> took <ms>ms
    - WARN: YYYY-MM-DD HH:MM:SS WARN Message
    """
    # Basic pattern for date and level
    # Match: 2024-01-01 12:00:00 INFO ...
    base_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$')
    match = base_pattern.match(line.strip())
    if not match:
        return None

    timestamp, level, content = match.groups()

    if level == "ERROR":
        return LogEntry(timestamp=timestamp, level=level, message=content)
    
    if level == "WARN":
        return LogEntry(timestamp=timestamp, level=level, message=content)
    
    if level == "INFO":
        # User action pattern: User 42 logged in
        user_match = re.match(r'^User (\S+) (.+)$', content)
        if user_match:
            uid, action = user_match.groups()
            return LogEntry(timestamp=timestamp, level=level, message=content, user_id=uid, action=action)
        
        # API call pattern: API /users/profile took 250ms
        api_match = re.match(r'^API (\S+) took (\d+)ms$', content)
        if api_match:
            endpoint, ms = api_match.groups()
            return LogEntry(timestamp=timestamp, level=level, message=content, endpoint=endpoint, latency_ms=int(ms))
            
    return LogEntry(timestamp=timestamp, level=level, message=content)

def extract_logs(path: str) -> List[LogEntry]:
    """Reads the log file and returns a list of parsed LogEntry objects."""
    entries = []
    if not os.path.exists(path):
        return entries
    
    with open(path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry:
                entries.append(entry)
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw entries into aggregated statistics.
    
    Returns:
        - error_counts: {message: count}
        - api_latencies: {endpoint: [latencies]}
        - active_sessions: Count of users who logged in but not out.
    """
    error_counts = {}
    api_latencies = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            msg = entry.message
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        elif entry.endpoint and entry.latency_ms is not None:
            api_latencies.setdefault(entry.endpoint, []).append(entry.latency_ms)
            
        elif entry.user_id:
            if entry.action and "logged in" in entry.action:
                sessions.add(entry.user_id)
            elif entry.action and "logged out" in entry.action:
                sessions.discard(entry.user_id)

    return error_counts, api_latencies, len(sessions)

def load_metrics(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """Saves aggregated metrics to SQLite using parameterized queries to prevent injection."""
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Use parameterized queries (?) instead of string formatting (%)
        for msg, count in error_counts.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """Generates the HTML report with the same structure as the original script."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_counts.items():
        out += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """Orchestrates the Extract, Transform, and Load process."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latencies, session_count = transform_data(entries)
    
    # Load
    load_metrics(error_counts, api_latencies)
    
    # Report
    generate_report(error_counts, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy data for verification if log file is missing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
