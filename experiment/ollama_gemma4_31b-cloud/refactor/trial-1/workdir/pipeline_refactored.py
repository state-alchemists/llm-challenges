import datetime
import os
import sqlite3
import re
from typing import List, Dict, Tuple
from dataclasses import dataclass

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
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex and extracts structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (.*)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = log_pattern.match(line)
            if not match:
                continue

            ts, lvl, msg = match.groups()
            
            if lvl == "ERROR":
                entries.append(LogEntry(timestamp=ts, level=lvl, message=msg))
            elif lvl == "WARN":
                entries.append(LogEntry(timestamp=ts, level=lvl, message=msg))
            elif lvl == "INFO":
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    entries.append(LogEntry(timestamp=ts, level=lvl, message=msg, user_id=uid, action=action))
                else:
                    api_match = api_pattern.search(msg)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        entries.append(LogEntry(timestamp=ts, level=lvl, message=msg, endpoint=endpoint, duration_ms=int(duration)))
    
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Transforms raw log entries into aggregates for the report and DB.
    
    Args:
        entries: List of extracted log entries.
        
    Returns:
        A tuple containing:
        - error_counts: Map of error messages to their frequency.
        - api_latencies: Map of endpoints to a list of their response times.
        - active_sessions: Final count of users who logged in but not out.
    """
    error_counts = {}
    api_latencies = {}
    sessions = set()

    for e in entries:
        if e.level == "ERROR":
            error_counts[e.message] = error_counts.get(e.message, 0) + 1
        elif e.level == "INFO":
            if e.user_id:
                if e.action and "logged in" in e.action:
                    sessions.add(e.user_id)
                elif e.action and "logged out" in e.action:
                    sessions.discard(e.user_id)
            elif e.endpoint:
                if e.duration_ms is not None:
                    api_latencies.setdefault(e.endpoint, []).append(e.duration_ms)

    return error_counts, api_latencies, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Loads aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error messages to counts.
        api_latencies: Map of endpoints to latency lists.
    """
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        # Parameterized inserts for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        c.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Calculate averages and insert for API metrics
        api_data = []
        for ep, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        
        c.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report from the aggregated data.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
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
    """
    Main orchestration function for the log processing pipeline.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latencies, session_count = transform_data(entries)
    
    # Load
    load_to_db(error_counts, api_latencies)
    
    # Report
    generate_report(error_counts, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy log if not exists for testing (retaining original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
