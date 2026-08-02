import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TypedDict
from collections import defaultdict

# Configuration via Environment Variables
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
    category: str  # ERR, USR, API, WARN
    message: str = ""
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency: Optional[int] = None

class ProcessingResult(TypedDict):
    errors: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int

def parse_logs(file_path: str) -> Tuple[List[LogEntry], int]:
    """
    Extracts and parses log lines using regular expressions.
    Returns a list of LogEntry objects and the count of active sessions.
    """
    entries = []
    sessions = set()
    
    # Regex patterns for different log types
    # General format: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)\s+(.*)$")
    user_pattern = re.compile(r"User (\w+)\s+(.*)$")
    api_pattern = re.compile(r"API (\S+)(?: took (\d+)ms)?$")

    if not os.path.exists(file_path):
        return entries, 0

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            timestamp, level, body = match.groups()

            if level == "ERROR":
                entries.append(LogEntry(timestamp, level, "ERR", message=body))
            elif level == "WARN":
                entries.append(LogEntry(timestamp, level, "WARN", message=body))
            elif level == "INFO":
                # Try User pattern
                u_match = user_pattern.match(body)
                if u_match:
                    user_id, action = u_match.groups()
                    if "logged in" in action:
                        sessions.add(user_id)
                    elif "logged out" in action:
                        sessions.discard(user_id)
                    entries.append(LogEntry(timestamp, level, "USR", user_id=user_id, action=action))
                    continue
                
                # Try API pattern
                a_match = api_pattern.match(body)
                if a_match:
                    endpoint, latency = a_match.groups()
                    entries.append(LogEntry(
                        timestamp, level, "API", 
                        endpoint=endpoint, 
                        latency=int(latency) if latency else 0
                    ))
    
    return entries, len(sessions)

def transform_metrics(entries: List[LogEntry]) -> ProcessingResult:
    """
    Transforms raw log entries into aggregated metrics.
    """
    error_counts = defaultdict(int)
    api_stats = defaultdict(list)

    for entry in entries:
        if entry.category == "ERR":
            error_counts[entry.message] += 1
        elif entry.category == "API" and entry.endpoint:
            api_stats[entry.endpoint].append(entry.latency or 0)

    return {
        "errors": dict(error_counts),
        "api_latencies": dict(api_stats),
        "active_sessions": 0 # Populated by parse_logs return value in main
    }

def load_to_db(metrics: ProcessingResult):
    """
    Loads processed metrics into the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Load Errors
        error_data = [
            (now, msg, count) 
            for msg, count in metrics["errors"].items()
        ]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Load API Metrics
        api_data = [
            (now, ep, sum(times)/len(times)) 
            for ep, times in metrics["api_latencies"].items()
        ]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: ProcessingResult, session_count: int, output_path: str = "report.html"):
    """
    Generates the HTML report based on the provided metrics.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in metrics["errors"].items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, times in metrics["api_latencies"].items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline():
    """
    Main orchestrator for the ETL pipeline.
    """
    # Extract
    entries, active_sessions = parse_logs(LOG_FILE)
    
    # Transform
    metrics = transform_metrics(entries)
    
    # Load
    load_to_db(metrics)
    generate_report(metrics, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup test data if not exists (preserving original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
