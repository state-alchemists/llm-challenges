import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
# DB_HOST, DB_PORT, DB_USER, DB_PASS are provided via env for compatibility with the original's print statement, 
# though sqlite3 doesn't use them.
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
    duration_ms: Optional[int] = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Pattern matches: YYYY-MM-DD HH:MM:SS LEVEL Message
    # Group 1: Timestamp, Group 2: Level, Group 3: Rest of the line
    line_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s(\w+)\s(.*)$")
    
    # Specific patterns for INFO logs
    user_pattern = re.compile(r"User\s(\S+)\s(.*)$")
    api_pattern = re.compile(r"API\s(\S+)(?:\s+took\s(\d+)ms)?.*$")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = line_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            
            entry = LogEntry(timestamp=timestamp, level=level, message=content)
            
            if level == "INFO":
                # Try User pattern
                user_match = user_pattern.search(content)
                if user_match:
                    entry.user_id, entry.action = user_match.groups()
                else:
                    # Try API pattern
                    api_match = api_pattern.search(content)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        entry.endpoint = endpoint
                        entry.duration_ms = int(duration) if duration else 0
            
            entries.append(entry)
            
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries into aggregates for the report and database.
    
    Args:
        entries: List of extracted LogEntry objects.
        
    Returns:
        A tuple containing:
        - Error counts: {message: count}
        - API latencies: {endpoint: [durations]}
        - Active session count: int
    """
    error_counts = {}
    api_latencies = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            if entry.user_id and entry.action:
                if "logged in" in entry.action:
                    sessions.add(entry.user_id)
                elif "logged out" in entry.action:
                    sessions.discard(entry.user_id)
            
            if entry.endpoint:
                api_latencies.setdefault(entry.endpoint, []).append(entry.duration_ms or 0)
                
    return error_counts, api_latencies, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Error message aggregates.
        api_latencies: Endpoint duration lists.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Load API metrics
        api_data = []
        for ep, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML system report.
    
    Args:
        error_counts: Error message aggregates.
        api_latencies: Endpoint duration lists.
        session_count: Number of active sessions.
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
    
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main orchestrator for the ETL pipeline.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latencies, session_count = transform_data(entries)
    
    # Load
    load_to_db(error_counts, api_latencies)
    generate_report(error_counts, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Maintain the mock data creation for testing consistency
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
