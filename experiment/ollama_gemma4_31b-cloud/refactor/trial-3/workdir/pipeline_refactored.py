import datetime
import os
import re
import sqlite3
from typing import Dict, List, TypedDict, Tuple, Optional

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
    action: Optional[str]
    endpoint: Optional[str]
    duration_ms: Optional[int]

class Metrics(TypedDict):
    error_counts: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex and extracts structured entries.
    
    Args:
        file_path: Path to the log file.
    Returns:
        A list of parsed log entries.
    """
    entries = []
    # Regex patterns for different log levels
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$')
    user_pattern = re.compile(r'User (\S+) (.*)')
    api_pattern = re.compile(r'API (\S+) took (\d+)ms')

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = base_pattern.match(line)
            if not match:
                continue

            timestamp, level, message = match.groups()
            entry: LogEntry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "user_id": None,
                "action": None,
                "endpoint": None,
                "duration_ms": None
            }

            if level == "INFO":
                user_match = user_pattern.search(message)
                if user_match:
                    entry["user_id"], entry["action"] = user_match.groups()
                
                api_match = api_pattern.search(message)
                if api_match:
                    entry["endpoint"], dur = api_match.groups()
                    entry["duration_ms"] = int(dur)

            entries.append(entry)
    return entries

def transform_logs(entries: List[LogEntry]) -> Metrics:
    """
    Aggregates log entries into metrics: error counts, API latencies, and active sessions.
    
    Args:
        entries: List of parsed log entries.
    Returns:
        Aggregated Metrics object.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: set = set()

    for entry in entries:
        level = entry["level"]
        msg = entry["message"]

        if level == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        elif level == "INFO":
            if entry["user_id"]:
                action = entry["action"] or ""
                if "logged in" in action:
                    sessions.add(entry["user_id"])
                elif "logged out" in action:
                    sessions.discard(entry["user_id"])
            
            if entry["endpoint"] and entry["duration_ms"] is not None:
                api_latencies.setdefault(entry["endpoint"], []).append(entry["duration_ms"])

    return {
        "error_counts": error_counts,
        "api_latencies": api_latencies,
        "active_sessions": len(sessions)
    }

def load_metrics(metrics: Metrics) -> None:
    """
    Saves metrics to the database using parameterized queries and generates an HTML report.
    
    Args:
        metrics: The aggregated metrics to store and report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        for msg, count in metrics["error_counts"].items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in metrics["api_latencies"].items():
            avg = sum(times) / len(times) if times else 0
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()
    finally:
        conn.close()

    # Generate HTML Report
    out = "<html lang='en'>\n<head><meta charset='UTF-8'><title>System Report</title></head>\n<body>\n"
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

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Orchestrates the ETL pipeline: Extract -> Transform -> Load.
    """
    entries = extract_logs(LOG_FILE)
    metrics = transform_logs(entries)
    load_metrics(metrics)
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure a log file exists for demonstration if it doesn't
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
