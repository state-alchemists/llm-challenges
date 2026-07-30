import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# --- Configuration ---
# Defaults provided for local development, overridden by env vars
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
    entry_type: str  # "ERR", "USR", "API", "WARN"
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex and extracts structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    # Regex patterns for different log types
    # General: 2024-01-01 12:00:00 LEVEL Message
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")
    
    # Specific patterns for content
    user_pattern = re.compile(r"User (\w+) (.*)")
    api_pattern = re.compile(r"API ([/\w\d\.\-]+) took (\d+)ms")

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = log_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            
            if level == "ERROR":
                entries.append(LogEntry(timestamp, level, content, "ERR"))
            elif level == "WARN":
                entries.append(LogEntry(timestamp, level, content, "WARN"))
            elif level == "INFO":
                # Try User match
                user_match = user_pattern.search(content)
                if user_match:
                    uid, action = user_match.groups()
                    entries.append(LogEntry(timestamp, level, content, "USR", user_id=uid, action=action))
                    continue
                
                # Try API match
                api_match = api_pattern.search(content)
                if api_match:
                    endpoint, duration = api_match.groups()
                    entries.append(LogEntry(timestamp, level, content, "API", endpoint=endpoint, duration_ms=int(duration)))
                    continue
    return entries

def transform_data(entries: List[LogEntry]):
    """
    Aggregates raw log entries into summaries for reporting and database storage.
    
    Args:
        entries: List of extracted LogEntry objects.
        
    Returns:
        A tuple containing (error_counts, api_stats, active_sessions)
    """
    error_counts: Dict[str, int] = {}
    api_stats: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in entries:
        if entry.entry_type == "ERR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        
        elif entry.entry_type == "API" and entry.endpoint and entry.duration_ms is not None:
            api_stats.setdefault(entry.endpoint, []).append(entry.duration_ms)
            
        elif entry.entry_type == "USR" and entry.user_id:
            if entry.action and "logged in" in entry.action:
                active_sessions[entry.user_id] = entry.timestamp
            elif entry.action and "logged out" in entry.action:
                active_sessions.pop(entry.user_id, None)

    return error_counts, api_stats, active_sessions

def load_to_db(error_counts: Dict[str, int], api_stats: Dict[str, List[int]]):
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Dictionary of error messages and their frequencies.
        api_stats: Dictionary of endpoints and their list of response times.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Parameterized inserts for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Parameterized inserts for API metrics
        api_data = []
        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, List[int]], active_sessions: Dict[str, str]):
    """
    Generates the HTML report based on the processed metrics.
    
    Args:
        error_counts: Dictionary of errors.
        api_stats: Dictionary of API latencies.
        active_sessions: Dictionary of currently active users.
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
    
    for ep, times in api_stats.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline():
    """
    Orchestrates the ETL pipeline: Extract -> Transform -> Load and Report.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_stats, active_sessions = transform_data(entries)
    
    # Load
    load_to_db(error_counts, api_stats)
    
    # Report
    generate_report(error_counts, api_stats, active_sessions)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy log if not present (matching original script behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
