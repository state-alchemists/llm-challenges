import datetime
import os
import re
import sqlite3
from typing import Dict, List, TypedDict, Optional, Tuple

# --- Configuration ---
# Using environment variables for all config to avoid hardcoding credentials and paths.
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
    latency_ms: Optional[int]

class ApiMetric(TypedDict):
    endpoint: str
    avg_ms: float

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regular expressions.
    
    Returns a list of LogEntry dictionaries containing extracted fields.
    """
    entries: List[LogEntry] = []
    
    # Regex patterns for different log levels/types
    # General format: YYYY-MM-DD HH:MM:SS LEVEL Message
    line_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$')
    user_pattern = re.compile(r'User (\w+) (.*)$')
    api_pattern = re.compile(r'API (\S+) took (\d+)ms')

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = line_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, message = match.groups()
            entry: LogEntry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "user_id": None,
                "action": None,
                "endpoint": None,
                "latency_ms": None
            }

            if level == "INFO":
                user_match = user_pattern.match(message)
                if user_match:
                    entry["user_id"], entry["action"] = user_match.groups()
                else:
                    api_match = api_pattern.search(message)
                    if api_match:
                        entry["endpoint"], lat = api_match.groups()
                        entry["latency_ms"] = int(lat)
            
            entries.append(entry)
            
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], List[ApiMetric], int]:
    """
    Processes raw log entries into summaries for the report and DB.
    
    Returns:
        - error_counts: Mapping of error messages to their frequency.
        - api_metrics: List of average latencies per endpoint.
        - active_sessions: Count of users who logged in but not out.
    """
    error_counts: Dict[str, int] = {}
    api_stats: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {} # user_id -> timestamp

    for entry in entries:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        elif entry["level"] == "INFO":
            if entry["user_id"] and entry["action"]:
                uid, action = entry["user_id"], entry["action"]
                if "logged in" in action:
                    sessions[uid] = entry["timestamp"]
                elif "logged out" in action:
                    sessions.pop(uid, None)
            
            if entry["endpoint"] and entry["latency_ms"] is not None:
                api_stats.setdefault(entry["endpoint"], []).append(entry["latency_ms"])

    api_metrics = [
        ApiMetric(endpoint=ep, avg_ms=sum(times)/len(times))
        for ep, times in api_stats.items()
    ]

    return error_counts, api_metrics, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_metrics: List[ApiMetric]) -> None:
    """
    Inserts aggregated metrics into the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        for msg, count in error_counts.items():
            # FIXED: Parameterized query to prevent SQL injection
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))
            
        for metric in api_metrics:
            # FIXED: Parameterized query to prevent SQL injection
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, metric["endpoint"], metric["avg_ms"]))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_metrics: List[ApiMetric], session_count: int) -> None:
    """
    Generates the HTML report with a summary of errors, API latency, and active sessions.
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
    
    for metric in api_metrics:
        html.append(f"<tr><td>{metric['endpoint']}</td><td>{round(metric['avg_ms'], 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main orchestrator for the Extract-Transform-Load pipeline.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_metrics, session_count = transform_data(entries)
    
    # Load
    load_to_db(error_counts, api_metrics)
    
    # Report
    generate_report(error_counts, api_metrics, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create dummy log if it doesn't exist for testing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
