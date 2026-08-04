import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TypedDict

# Configuration from environment variables
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
    endpoint: Optional[str]
    duration_ms: Optional[int]

@dataclass
class ProcessedMetrics:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of structured log entries.
    """
    entries = []
    # Pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$')
    
    # Specific patterns for structured messages
    user_pattern = re.compile(r'User (\d+) (logged in|logged out)')
    api_pattern = re.compile(r'API ([/\w\d_/]+) took (\d+)ms')

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
                
            ts, lvl, msg = match.groups()
            entry: LogEntry = {
                "timestamp": ts,
                "level": lvl,
                "message": msg,
                "user_id": None,
                "endpoint": None,
                "duration_ms": None
            }

            if lvl == "INFO":
                # Check for user activity
                u_match = user_pattern.search(msg)
                if u_match:
                    entry["user_id"] = u_match.group(1)
                    # Note: original logic used the whole action string, 
                    # but extracted the ID. We keep the message for context.
                
                # Check for API calls
                a_match = api_pattern.search(msg)
                if a_match:
                    entry["endpoint"] = a_match.group(1)
                    entry["duration_ms"] = int(a_match.group(2))
            
            entries.append(entry)
            
    return entries

def transform_data(entries: List[LogEntry]) -> ProcessedMetrics:
    """
    Transforms raw log entries into aggregated metrics.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        ProcessedMetrics object containing aggregated totals and lists.
    """
    metrics = ProcessedMetrics()
    
    for entry in entries:
        lvl = entry["level"]
        msg = entry["message"]
        
        if lvl == "ERROR":
            metrics.error_counts[msg] = metrics.error_counts.get(msg, 0) + 1
            
        elif lvl == "INFO":
            if entry["user_id"]:
                if "logged in" in msg:
                    metrics.active_sessions.add(entry["user_id"])
                elif "logged out" in msg:
                    metrics.active_sessions.discard(entry["user_id"])
            
            if entry["endpoint"] and entry["duration_ms"] is not None:
                metrics.api_latencies.setdefault(entry["endpoint"], []).append(entry["duration_ms"])
                
    return metrics

def load_to_db(metrics: ProcessedMetrics) -> None:
    """
    Loads processed metrics into the SQLite database using parameterized queries.
    
    Args:
        metrics: The processed metrics to store.
    """
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        # Insert errors
        error_data = [(now, msg, count) for msg, count in metrics.error_counts.items()]
        c.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Insert API metrics
        api_data = []
        for ep, times in metrics.api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        c.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: ProcessedMetrics, output_path: str = "report.html") -> None:
    """
    Generates an HTML report from the processed metrics.
    
    Args:
        metrics: The processed metrics.
        output_path: Path to the output HTML file.
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
    Main execution pipeline: Extract -> Transform -> Load -> Report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    # 1. Extract
    raw_entries = extract_logs(LOG_FILE)
    
    # 2. Transform
    metrics = transform_data(raw_entries)
    
    # 3. Load
    load_to_db(metrics)
    
    # 4. Report
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock data creation for local testing if log file missing (preserving original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
