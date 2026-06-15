import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

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
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PipelineData:
    errors: List[LogEntry] = field(default_factory=list)
    api_calls: List[Dict[str, Any]] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)

def parse_logs(file_path: str) -> PipelineData:
    """
    Extracts structured data from server logs using regex.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A PipelineData object containing parsed logs.
    """
    data = PipelineData()
    
    # Regex patterns for different log types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
    user_pattern = re.compile(r"User (\S+) (logged in|logged out)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = base_pattern.match(line)
            if not match:
                continue
            
            ts, level, msg = match.groups()

            if level == "ERROR":
                data.errors.append(LogEntry(ts, level, msg))
            
            elif level == "INFO":
                # Check for User activity
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    if action == "logged in":
                        data.active_sessions[uid] = ts
                    elif action == "logged out":
                        data.active_sessions.pop(uid, None)
                    continue
                
                # Check for API activity
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint, duration = api_match.groups()
                    data.api_calls.append({
                        "timestamp": ts,
                        "endpoint": endpoint,
                        "duration": int(duration)
                    })
            
            elif level == "WARN":
                # Keep warn messages as errors for summary if desired, 
                # but original code added them to d_list. 
                # We'll treat them as general entries.
                data.errors.append(LogEntry(ts, level, msg))

    return data

def transform_data(data: PipelineData) -> tuple[Dict[str, int], Dict[str, float]]:
    """
    Aggregates raw log entries into metrics.
    
    Args:
        data: Parsed log data.
        
    Returns:
        A tuple of (error_counts, api_avg_latency).
    """
    # Count errors
    error_counts = {}
    for err in data.errors:
        # Original code only counted ERROR level, not WARN in the final report
        if err.level == "ERROR":
            error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # Calculate API avg latency
    endpoint_stats = {}
    for call in data.api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["duration"])
    
    api_avg_latency = {ep: sum(times)/len(times) for ep, times in endpoint_stats.items()}
    
    return error_counts, api_avg_latency

def load_metrics(error_counts: Dict[str, int], api_latency: Dict[str, float]) -> None:
    """
    Loads metrics into the local SQLite database using parameterized queries.
    
    Args:
        error_counts: Dictionary of error messages and their counts.
        api_latency: Dictionary of endpoints and their average latency.
    """
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        # Parameterized inserts to prevent SQL injection
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))
            
        for ep, avg in api_latency.items():
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
            
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latency: Dict[str, float], session_count: int) -> None:
    """
    Generates an HTML report.
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
    
    for ep, avg in api_latency.items():
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline():
    """
    Main orchestration for the pipeline.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    # Extract
    data = parse_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latency = transform_data(data)
    
    # Load
    load_metrics(error_counts, api_latency)
    
    # Report
    generate_report(error_counts, api_latency, len(data.active_sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Seed log file if missing for demo purposes
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
