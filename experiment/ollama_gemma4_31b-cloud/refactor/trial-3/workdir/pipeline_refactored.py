import os
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# --- Configuration ---
# Use environment variables for all config to avoid hardcoding credentials and paths
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_FILE = os.getenv("REPORT_FILE", "report.html")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured entries.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Regex patterns for different log types
    # General pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    
    # Specific patterns for content extraction
    user_pattern = re.compile(r"User (\w+) (logged in|logged out)")
    api_pattern = re.compile(r"API ([^\s]+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            ts, lvl, msg = match.groups()
            entry = LogEntry(timestamp=ts, level=lvl, message=msg)

            if lvl == "INFO":
                # Try User parsing
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    entry.metadata = {"type": "USER", "uid": uid, "action": action}
                else:
                    # Try API parsing
                    api_match = api_pattern.search(msg)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        entry.metadata = {"type": "API", "endpoint": endpoint, "ms": int(duration)}
            
            entries.append(entry)
            
    return entries

def transform_metrics(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries to aggregate error counts, API latencies, and active sessions.
    
    Args:
        entries: List of extracted LogEntry objects.
        
    Returns:
        A tuple containing:
        - error_counts: Map of error message to occurrence count.
        - api_latencies: Map of endpoint to list of response times.
        - active_sessions: Final count of active user sessions.
    """
    error_counts = {}
    api_latencies = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        
        elif entry.level == "INFO" and entry.metadata.get("type") == "USER":
            uid = entry.metadata["uid"]
            action = entry.metadata["action"]
            if action == "logged in":
                sessions.add(uid)
            elif action == "logged out":
                sessions.discard(uid)
                
        elif entry.level == "INFO" and entry.metadata.get("type") == "API":
            ep = entry.metadata["endpoint"]
            api_latencies.setdefault(ep, []).append(entry.metadata["ms"])

    return error_counts, api_latencies, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error message to frequency.
        api_latencies: Map of endpoint to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Fix SQL Injection: Use parameterized queries (?)
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report with the specified metrics.
    
    Args:
        error_counts: Map of error message to frequency.
        api_latencies: Map of endpoint to list of latencies.
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

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main execution flow: Extract -> Transform -> Load -> Report.
    """
    # 1. Extract
    entries = extract_logs(LOG_FILE)
    
    # 2. Transform
    error_counts, api_latencies, session_count = transform_metrics(entries)
    
    # 3. Load
    load_to_db(error_counts, api_latencies)
    
    # 4. Report
    generate_report(error_counts, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure test data exists if log file is missing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
