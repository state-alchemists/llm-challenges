import os
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# --- Configuration ---
# Use environment variables for configuration to avoid hardcoding credentials and paths.
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Data Models ---

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

@dataclass
class PipelineMetrics:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

# --- ETL Logic ---

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regular expressions.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects parsed from the file.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    # Regex patterns for different log types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s(\w+)\s(.*)$")
    user_pattern = re.compile(r"User\s(\w+)\s(.*)$")
    api_pattern = re.compile(r"API\s([^\s]+)(?:\stook\s(\d+)ms)?$")

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, message = match.groups()
            
            entry = LogEntry(timestamp=timestamp, level=level, message=message)
            
            if level == "INFO":
                # Check for User action
                user_match = user_pattern.search(message)
                if user_match:
                    uid, action = user_match.groups()
                    entry.user_id = uid
                    entry.action = action
                # Check for API call
                api_match = api_pattern.search(message)
                if api_match:
                    endpoint, latency = api_match.groups()
                    entry.endpoint = endpoint
                    entry.latency_ms = int(latency) if latency else 0
            
            entries.append(entry)
            
    return entries

def transform_metrics(entries: List[LogEntry]) -> PipelineMetrics:
    """
    Aggregates log entries into a set of metrics.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A PipelineMetrics object containing summarized data.
    """
    metrics = PipelineMetrics()
    
    for entry in entries:
        if entry.level == "ERROR":
            msg = entry.message
            metrics.error_counts[msg] = metrics.error_counts.get(msg, 0) + 1
            
        elif entry.level == "INFO" and entry.user_id:
            if "logged in" in entry.action:
                metrics.active_sessions.add(entry.user_id)
            elif "logged out" in entry.action:
                metrics.active_sessions.discard(entry.user_id)
                
        elif entry.level == "INFO" and entry.endpoint:
            metrics.api_latencies.setdefault(entry.endpoint, []).append(entry.latency_ms or 0)
            
    return metrics

def load_to_db(metrics: PipelineMetrics) -> None:
    """
    Persists aggregated metrics to the database using parameterized queries.
    
    Args:
        metrics: The processed metrics to store.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Securely insert error counts
        error_data = [(now, msg, count) for msg, count in metrics.error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Securely insert API metrics
        api_data = []
        for ep, latencies in metrics.api_latencies.items():
            avg = sum(latencies) / len(latencies) if latencies else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: PipelineMetrics, output_path: str = "report.html") -> None:
    """
    Generates an HTML report from the aggregated metrics.
    
    Args:
        metrics: The metrics to report.
        output_path: Destination file for the HTML report.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in metrics.error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, latencies in metrics.api_latencies.items():
        avg = sum(latencies) / len(latencies) if latencies else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(metrics.active_sessions)} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """Main orchestration function for the log processing pipeline."""
    entries = extract_logs(LOG_FILE)
    metrics = transform_metrics(entries)
    load_to_db(metrics)
    generate_report(metrics)
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure a log file exists for demonstration/testing as per original script
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
