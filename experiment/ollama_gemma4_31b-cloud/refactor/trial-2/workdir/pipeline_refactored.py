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
    latency_ms: Optional[int] = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file and extracts structured entries using regex.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Regex patterns for different log types
    # Generic: YYYY-MM-DD HH:MM:SS LEVEL ...
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (logged in|logged out)")
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
            
            entry = LogEntry(timestamp=timestamp, level=level, message=content)

            if level == "INFO":
                # Check for User activity
                user_match = user_pattern.search(content)
                if user_match:
                    entry.user_id, entry.action = user_match.groups()
                
                # Check for API activity
                api_match = api_pattern.search(content)
                if api_match:
                    entry.endpoint, lat_str = api_match.groups()
                    entry.latency_ms = int(lat_str)

            entries.append(entry)
    
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Aggregates log entries into error counts, API latencies, and active session count.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A tuple containing:
        - error_summary: Dict mapping error message to frequency.
        - api_stats: Dict mapping endpoint to list of response times.
        - active_sessions: Count of users who logged in but didn't log out.
    """
    error_summary = {}
    api_stats = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            if entry.user_id and entry.action:
                if entry.action == "logged in":
                    sessions.add(entry.user_id)
                elif entry.action == "logged out":
                    sessions.discard(entry.user_id)
            
            if entry.endpoint and entry.latency_ms is not None:
                api_stats.setdefault(entry.endpoint, []).append(entry.latency_ms)

    return error_summary, api_stats, len(sessions)

def load_to_db(error_summary: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_summary: Error message frequencies.
        api_stats: Endpoint latency lists.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load Errors
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Load API Metrics
        api_data = [(now, ep, sum(times)/len(times)) for ep, times in api_stats.items() if times]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_summary: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report file.
    
    Args:
        error_summary: Error message frequencies.
        api_stats: Endpoint latency lists.
        session_count: Total active sessions.
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
    for ep, times in api_stats.items():
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
    Main execution flow: Extract -> Transform -> Load.
    """
    entries = extract_logs(LOG_FILE)
    error_summary, api_stats, session_count = transform_logs(entries)
    
    load_to_db(error_summary, api_stats)
    generate_report(error_summary, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Bootstrap a sample log file if it doesn't exist (matching original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
