import os
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# Configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
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

def extract_logs(file_path: str) -> Tuple[List[LogEntry], Dict[str, str]]:
    """
    Parses server logs using regex into structured LogEntry objects.
    Returns a tuple of all entries and the map of currently active sessions.
    """
    entries = []
    sessions = {}

    # Regex patterns
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$"
    user_pattern = r"User (\d+) (logged in|logged out|.+)$"
    api_pattern = r"API ([^\s]+) took (\d+)ms"

    if not os.path.exists(file_path):
        return [], {}

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = re.match(base_pattern, line)
            if not match:
                continue

            dt, lvl, msg = match.groups()
            entry = LogEntry(timestamp=dt, level=lvl, message=msg)

            if lvl == "INFO":
                # Check for User activity
                user_match = re.search(user_pattern, msg)
                if user_match:
                    uid, action = user_match.groups()
                    entry.user_id = uid
                    entry.action = action
                    if action == "logged in":
                        sessions[uid] = dt
                    elif action == "logged out":
                        sessions.pop(uid, None)
                
                # Check for API activity
                api_match = re.search(api_pattern, msg)
                if api_match:
                    endpoint, latency = api_match.groups()
                    entry.endpoint = endpoint
                    entry.latency_ms = int(latency)

            entries.append(entry)
    
    return entries, sessions

def transform_metrics(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Aggregates raw log entries into error counts and API latency lists.
    """
    error_counts = {}
    api_latencies = {}

    for entry in entries:
        if entry.level == "ERROR":
            msg = entry.message
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        if entry.endpoint and entry.latency_ms is not None:
            api_latencies.setdefault(entry.endpoint, []).append(entry.latency_ms)

    return error_counts, api_latencies

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    """
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized inserts for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Parameterized inserts for API metrics
        api_data = []
        for ep, latencies in api_latencies.items():
            avg = sum(latencies) / len(latencies)
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], active_sessions_count: int) -> None:
    """
    Generates the final report.html with summarized metrics.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, latencies in api_latencies.items():
        avg = sum(latencies) / len(latencies)
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{active_sessions_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main execution flow: Extract -> Transform -> Load.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    # 1. Extract
    entries, sessions = extract_logs(LOG_FILE)
    
    # 2. Transform
    error_counts, api_latencies = transform_metrics(entries)
    
    # 3. Load (DB + Report)
    load_to_db(error_counts, api_latencies)
    generate_report(error_counts, api_latencies, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure mock log exists for demonstration as per original script
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
