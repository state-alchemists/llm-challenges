import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# --- Configuration ---
# Using environment variables for security and flexibility
DB_PATH = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE = os.getenv("PIPELINE_LOG_FILE", "server.log")
DB_HOST = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS = os.getenv("PIPELINE_DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None

@dataclass
class ProcessedMetrics:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def extract_logs(file_path: str) -> List[str]:
    """Reads raw lines from the log file."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        return f.readlines()

def transform_logs(lines: List[str]) -> Tuple[ProcessedMetrics, List[LogEntry]]:
    """
    Parses raw log lines into structured data and aggregates metrics.
    
    Uses regex to identify log levels and specific patterns for 
    Users and API calls.
    """
    metrics = ProcessedMetrics()
    entries = []
    
    # Regex patterns
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (.*)$")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    for line in lines:
        line = line.strip()
        match = base_pattern.match(line)
        if not match:
            continue
        
        dt, lvl, msg = match.groups()
        entry = LogEntry(timestamp=dt, level=lvl, message=msg)

        if lvl == "ERROR":
            metrics.error_counts[msg] = metrics.error_counts.get(msg, 0) + 1
        
        elif lvl == "INFO":
            # User activity
            user_match = user_pattern.search(msg)
            if user_match:
                uid, action = user_match.groups()
                entry.user_id = uid
                entry.action = action
                if "logged in" in action:
                    metrics.active_sessions.add(uid)
                elif "logged out" in action:
                    metrics.active_sessions.discard(uid)
            
            # API activity
            api_match = api_pattern.search(msg)
            if api_match:
                endpoint, dur = api_match.groups()
                entry.endpoint = endpoint
                entry.duration_ms = int(dur)
                metrics.api_latencies.setdefault(endpoint, []).append(entry.duration_ms)
        
        elif lvl == "WARN":
            # Warnings are captured in entries but not aggregated in specific summary
            pass
            
        entries.append(entry)
        
    return metrics, entries

def load_to_db(metrics: ProcessedMetrics) -> None:
    """
    Persists aggregated metrics to the database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Fix SQL Injection: Use parameterized queries (?)
        error_data = [(now, msg, count) for msg, count in metrics.error_counts.items()]
        c.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        api_data = [
            (now, ep, sum(times)/len(times)) 
            for ep, times in metrics.api_latencies.items() 
            if times
        ]
        c.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: ProcessedMetrics, output_path: str = "report.html") -> None:
    """
    Generates an HTML report based on the processed metrics.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    # Error Summary
    html.append("<h1>Error Summary</h1>")
    html.append("<ul>")
    for msg, count in metrics.error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    html.append("</ul>")

    # API Latency
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in metrics.api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    html.append("</table>")

    # Active Sessions
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(metrics.active_sessions)} user(s) currently active</p>")
    
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main orchestration function for the log processing pipeline.
    """
    # Extract
    raw_lines = extract_logs(LOG_FILE)
    
    # Transform
    metrics, _ = transform_logs(raw_lines)
    
    # Load
    load_to_db(metrics)
    
    # Report
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure sample log exists for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
