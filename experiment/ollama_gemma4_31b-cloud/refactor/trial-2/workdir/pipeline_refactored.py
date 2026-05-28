import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Configuration using environment variables
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
    type: str  # 'ERR', 'USR', 'API', 'WARN'
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency: Optional[int] = None

def parse_logs(file_path: str) -> Tuple[List[LogEntry], Dict[str, str], List[Dict]]:
    """
    Extracts data from server logs using regex.
    
    Returns:
        - List of LogEntry objects
        - Dictionary of active sessions {uid: timestamp}
        - List of API calls [{'endpoint': str, 'ms': int}]
    """
    entries = []
    sessions = {}
    api_calls = []
    
    # Regex patterns for different log types
    # Basic format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<level>\w+) (?P<msg>.*)$")
    user_pattern = re.compile(r"User (?P<uid>\S+) (?P<action>.*)$")
    api_pattern = re.compile(r"API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")

    if not os.path.exists(file_path):
        return entries, sessions, api_calls

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = base_pattern.match(line)
            if not match:
                continue
            
            ts, lvl, msg = match.groups()
            
            if lvl == "ERROR":
                entries.append(LogEntry(ts, lvl, msg, "ERR"))
            
            elif lvl == "WARN":
                entries.append(LogEntry(ts, lvl, msg, "WARN"))
            
            elif lvl == "INFO":
                user_match = user_pattern.match(msg)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action")
                    if "logged in" in action:
                        sessions[uid] = ts
                    elif "logged out" in action:
                        sessions.pop(uid, None)
                    entries.append(LogEntry(ts, lvl, msg, "USR", user_id=uid, action=action))
                    continue
                
                api_match = api_pattern.match(msg)
                if api_match:
                    ep = api_match.group("endpoint")
                    ms = int(api_match.group("ms")) if api_match.group("ms") else 0
                    api_calls.append({"endpoint": ep, "ms": ms})
                    entries.append(LogEntry(ts, lvl, msg, "API", endpoint=ep, latency=ms))

    return entries, sessions, api_calls

def load_to_db(api_calls: List[Dict], errors: Dict[str, int]):
    """
    Loads summarized metrics into the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    timestamp = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Insert Error summaries
        error_data = [(timestamp, msg, count) for msg, count in errors.items()]
        c.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Process API metrics
        endpoint_stats = {}
        for call in api_calls:
            ep = call["endpoint"]
            endpoint_stats.setdefault(ep, []).append(call["ms"])

        api_data = [
            (timestamp, ep, sum(times) / len(times)) 
            for ep, times in endpoint_stats.items()
        ]
        c.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_calls: List[Dict], active_sessions_count: int):
    """
    Generates the report.html based on summarized data.
    """
    # Calculate API averages for the table
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline():
    """
    Main execution flow: Extract -> Transform -> Load -> Report.
    """
    # 1. Extract
    entries, sessions, api_calls = parse_logs(LOG_FILE)
    
    # 2. Transform
    error_counts = {}
    for entry in entries:
        if entry.type == "ERR":
            msg = entry.message
            error_counts[msg] = error_counts.get(msg, 0) + 1
            
    # 3. Load
    load_to_db(api_calls, error_counts)
    
    # 4. Report
    generate_report(error_counts, api_calls, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure log file exists for the demonstration/test as in the original script
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
