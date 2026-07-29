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

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    latency_ms: int | None = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regular expressions.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    # Pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    line_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
    # Pattern for User actions: User <id> <action>
    user_pattern = re.compile(r"User (\w+) (.+)")
    # Pattern for API calls: API <endpoint> took <ms>ms
    api_pattern = re.compile(r"API ([^\s]+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = line_pattern.match(line)
            if not match:
                continue

            timestamp, level, message = match.groups()
            entry = LogEntry(timestamp=timestamp, level=level, message=message)

            if level == "INFO":
                user_match = user_pattern.search(message)
                if user_match:
                    entry.user_id, entry.action = user_match.groups()
                
                api_match = api_pattern.search(message)
                if api_match:
                    entry.endpoint, latency_str = api_match.groups()
                    entry.latency_ms = int(latency_str)
            
            entries.append(entry)
            
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Transforms raw log entries into aggregates for reporting and storage.
    
    Args:
        entries: List of parsed LogEntry objects.
        
    Returns:
        A tuple containing:
        - error_counts: Map of error message to occurrence count.
        - api_latencies: Map of endpoint to list of latencies.
        - active_sessions: Count of currently active users.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_users = set()

    for e in entries:
        if e.level == "ERROR":
            error_counts[e.message] = error_counts.get(e.message, 0) + 1
        
        elif e.level == "INFO":
            if e.user_id:
                if e.action and "logged in" in e.action:
                    active_users.add(e.user_id)
                elif e.action and "logged out" in e.action:
                    active_users.discard(e.user_id)
            
            if e.endpoint and e.latency_ms is not None:
                api_latencies.setdefault(e.endpoint, []).append(e.latency_ms)
                
    return error_counts, api_latencies, len(active_users)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists processed metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error message to count.
        api_latencies: Map of endpoint to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int, output_path: str = "report.html") -> None:
    """
    Generates the HTML report with system metrics.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    html.append("<h1>Error Summary</h1>")
    html.append("<ul>")
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

    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main orchestration function for the log processing pipeline.
    """
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
    # Ensure dummy log exists for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
