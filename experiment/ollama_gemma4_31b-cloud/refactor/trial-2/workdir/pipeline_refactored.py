import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# --- Configuration ---
# Defaults provided for local development; override via environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS") # Required for production

# --- Data Models ---

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class ErrorEntry(LogEntry):
    count: int = 1

@dataclass
class UserAction:
    timestamp: str
    user_id: str
    action: str

@dataclass
class ApiMetric:
    timestamp: str
    endpoint: str
    duration_ms: int

@dataclass
class PipelineData:
    errors: List[ErrorEntry] = field(default_factory=list)
    api_metrics: List[ApiMetric] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)

# --- Extraction ---

def parse_log_line(line: str) -> Tuple[Optional[LogEntry], Optional[UserAction], Optional[ApiMetric]]:
    """
    Parses a single log line using regex to extract structured data.
    
    Returns a tuple of (GeneralEntry, UserAction, ApiMetric), where only one 
    (or none) will be non-None depending on the log level and content.
    """
    # Generic pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = r'^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(INFO|ERROR|WARN)\s+(.*)$'
    match = re.match(base_pattern, line)
    if not match:
        return None, None, None

    timestamp, level, content = match.groups()

    if level == "ERROR":
        return ErrorEntry(timestamp, level, content), None, None

    if level == "WARN":
        return LogEntry(timestamp, level, content), None, None

    if level == "INFO":
        # User action: INFO User <id> <action>
        user_match = re.search(r'User\s+(\S+)\s+(.*)$', content)
        if user_match:
            uid, action = user_match.groups()
            return None, UserAction(timestamp, uid, action), None

        # API metric: INFO API <endpoint> took <ms>ms
        api_match = re.search(r'API\s+(\S+)\s+took\s+(\d+)ms', content)
        if api_match:
            endpoint, duration = api_match.groups()
            return None, None, ApiMetric(timestamp, endpoint, int(duration))

    return LogEntry(timestamp, level, content), None, None

def extract_logs(file_path: str) -> PipelineData:
    """Reads the log file and extracts structured data into a PipelineData object."""
    data = PipelineData()
    
    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            entry, user_act, api_met = parse_log_line(line)
            
            if isinstance(entry, ErrorEntry):
                data.errors.append(entry)
            elif isinstance(entry, LogEntry) and entry.level == "WARN":
                # Original script tracked WARN in d_list but didn't use it for report/DB
                pass 
            
            if user_act:
                if "logged in" in user_act.action:
                    data.active_sessions[user_act.user_id] = user_act.timestamp
                elif "logged out" in user_act.action:
                    data.active_sessions.pop(user_act.user_id, None)
            
            if api_met:
                data.api_metrics.append(api_met)
                
    return data

# --- Transformation ---

def transform_metrics(raw_data: PipelineData) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Aggregates raw extracted data into summaries for the report and DB.
    
    Returns:
        error_counts: Mapping of error message to occurrence count.
        api_latencies: Mapping of endpoint to list of durations.
    """
    error_counts: Dict[str, int] = {}
    for err in raw_data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_latencies: Dict[str, List[int]] = {}
    for metric in raw_data.api_metrics:
        api_latencies.setdefault(metric.endpoint, []).append(metric.duration_ms)

    return error_counts, api_latencies

# --- Loading ---

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """Persists aggregated metrics to the SQLite database using parameterized queries."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()
        
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for endpoint, times in api_latencies.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, endpoint, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """Generates the final HTML report."""
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
    
    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open("report.html", "w") as f:
        f.write("\n".join(html))

# --- Main Pipeline ---

def run_pipeline() -> None:
    """Coordinates the ETL process."""
    # Extract
    raw_data = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latencies = transform_metrics(raw_data)
    
    # Load
    load_to_db(error_counts, api_latencies)
    generate_report(error_counts, api_latencies, len(raw_data.active_sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure log file exists for testing (matching original script behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
