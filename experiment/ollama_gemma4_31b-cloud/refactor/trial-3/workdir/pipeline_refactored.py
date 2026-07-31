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
DB_PASS = os.getenv("DB_PASS")

# Log parsing regex patterns
# Example line: 2024-01-01 12:00:00 INFO User 42 logged in
# Example line: 2024-01-01 12:05:00 ERROR Database timeout
LOG_PATTERN = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<level>INFO|ERROR|WARN) (?P<message>.*)"
)
USER_PATTERN = re.compile(r"User (?P<uid>\S+) (?P<action>.*)")
API_PATTERN = re.compile(r"API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    uid: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration: Optional[int] = None

class ProcessedMetrics(TypedDict):
    error_counts: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file and extracts structured log entries.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = LOG_PATTERN.match(line)
            if not match:
                continue
            
            data = match.groupdict()
            entry = LogEntry(
                timestamp=data["date"],
                level=data["level"],
                message=data["message"]
            )

            if entry.level == "INFO":
                # Check for User activity
                user_match = USER_PATTERN.match(entry.message)
                if user_match:
                    u_data = user_match.groupdict()
                    entry.uid = u_data["uid"]
                    entry.action = u_data["action"]
                else:
                    # Check for API activity
                    api_match = API_PATTERN.match(entry.message)
                    if api_match:
                        a_data = api_match.groupdict()
                        entry.endpoint = a_data["endpoint"]
                        entry.duration = int(a_data["duration"]) if a_data["duration"] else 0
            
            entries.append(entry)
    
    return entries

def transform_logs(entries: List[LogEntry]) -> ProcessedMetrics:
    """
    Aggregates log entries into metrics for the report.
    
    Args:
        entries: List of structured log entries.
        
    Returns:
        A dictionary containing error counts, API latencies, and active session count.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        
        elif entry.level == "INFO" and entry.uid:
            if "logged in" in (entry.action or ""):
                sessions[entry.uid] = entry.timestamp
            elif "logged out" in (entry.action or ""):
                sessions.pop(entry.uid, None)
        
        elif entry.level == "INFO" and entry.endpoint:
            api_latencies.setdefault(entry.endpoint, []).append(entry.duration or 0)

    return {
        "error_counts": error_counts,
        "api_latencies": api_latencies,
        "active_sessions": len(sessions)
    }

def load_to_db(metrics: ProcessedMetrics) -> None:
    """
    Saves the aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        metrics: The processed metrics to store.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Load errors
        for msg, count in metrics["error_counts"].items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        # Load API metrics
        for ep, times in metrics["api_latencies"].items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()

def generate_report(metrics: ProcessedMetrics, output_path: str = "report.html") -> None:
    """
    Generates an HTML report based on the processed metrics.
    
    Args:
        metrics: The processed metrics.
        output_path: Path to save the HTML report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics["error_counts"].items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics["api_latencies"].items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{metrics['active_sessions']} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_path, "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Main orchestration function for the log processing pipeline.
    """
    entries = extract_logs(LOG_FILE)
    metrics = transform_logs(entries)
    load_to_db(metrics)
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create dummy log for testing if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
