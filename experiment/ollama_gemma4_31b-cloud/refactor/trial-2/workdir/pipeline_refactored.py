import os
import re
import sqlite3
import datetime
from typing import List, Dict, Any, Tuple, NamedTuple
from dataclasses import dataclass

# Configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_FILE = "report.html"

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    metadata: Dict[str, Any]

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured entries.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Regex to capture: date time level message
    # Example: 2024-01-01 12:00:00 INFO User 42 logged in
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = log_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            metadata = {}

            if level == "INFO":
                if "User " in content:
                    # Regex for "User <id> <action>"
                    user_match = re.search(r"User (\w+) (.+)", content)
                    if user_match:
                        uid, action = user_match.groups()
                        metadata = {"type": "USER", "user_id": uid, "action": action}
                elif "API " in content:
                    # Regex for "API <endpoint> took <ms>ms"
                    api_match = re.search(r"API (\S+) took (\d+)ms", content)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        metadata = {"type": "API", "endpoint": endpoint, "ms": int(duration)}
            
            entries.append(LogEntry(timestamp, level, content, metadata))
            
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes log entries to aggregate error counts, API latencies, and active sessions.
    
    Args:
        entries: List of extracted log entries.
        
    Returns:
        A tuple containing:
        - error_summary: Map of error message to count.
        - api_stats: Map of endpoint to list of latencies.
        - active_sessions_count: Number of users who logged in but haven't logged out.
    """
    error_summary = {}
    api_stats = {}
    active_sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            meta = entry.metadata
            if meta.get("type") == "USER":
                uid = meta["user_id"]
                action = meta["action"]
                if "logged in" in action:
                    active_sessions.add(uid)
                elif "logged out" in action:
                    active_sessions.discard(uid)
            
            elif meta.get("type") == "API":
                endpoint = meta["endpoint"]
                latency = meta["ms"]
                api_stats.setdefault(endpoint, []).append(latency)
                
    return error_summary, api_stats, len(active_sessions)

def load_metrics(error_summary: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_summary: Map of error message to count.
        api_stats: Map of endpoint to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized insert for errors
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Calculate averages and insert for API metrics
        api_data = []
        for endpoint, latencies in api_stats.items():
            avg = sum(latencies) / len(latencies)
            api_data.append((now, endpoint, avg))
        
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        conn.commit()

def generate_report(error_summary: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates an HTML report from the processed metrics.
    
    Args:
        error_summary: Map of error message to count.
        api_stats: Map of endpoint to list of latencies.
        session_count: Current number of active sessions.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    html.append("<h1>Error Summary</h1>")
    html.append("<ul>")
    for msg, count in error_summary.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    html.append("</ul>")

    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, latencies in api_stats.items():
        avg = sum(latencies) / len(latencies)
        html.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    html.append("</table>")

    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    
    html.append("</body>")
    html.append("</html>")

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(html))

def main() -> None:
    """
    Main pipeline execution: Extract -> Transform -> Load -> Report.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_summary, api_stats, session_count = transform_data(entries)
    
    # Load
    load_metrics(error_summary, api_stats)
    
    # Report
    generate_report(error_summary, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure sample log exists for demonstration if it's missing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    main()
