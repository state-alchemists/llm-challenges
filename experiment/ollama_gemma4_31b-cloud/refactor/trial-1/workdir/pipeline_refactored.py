import datetime
import os
import re
import sqlite3
from typing import Dict, List, TypedDict, Optional, Tuple

# --- Configuration ---
# Use environment variables for all sensitive/dynamic configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Types ---
class LogEntry(TypedDict):
    timestamp: str
    level: str
    message: str
    user_id: Optional[str]
    action: Optional[str]
    endpoint: Optional[str]
    latency: Optional[int]

class PipelineMetrics(TypedDict):
    error_counts: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int

# --- Extract Phase ---
def parse_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry dictionaries.
    """
    entries: List[LogEntry] = []
    
    # Log format: YYYY-MM-DD HH:MM:SS LEVEL Message
    # Example: 2024-01-01 12:00:00 INFO User 42 logged in
    # Example: 2024-01-01 12:05:00 ERROR Database timeout
    # Example: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    
    base_pattern = r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>\S+) (?P<msg>.*)$"
    user_pattern = r"User (?P<uid>\S+) (?P<action>.*)$"
    api_pattern = r"API (?P<ep>\S+) took (?P<ms>\d+)ms"

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = re.match(base_pattern, line)
            if not match:
                continue
                
            ts, lvl, msg = match.group("ts"), match.group("lvl"), match.group("msg")
            entry: LogEntry = {"timestamp": ts, "level": lvl, "message": msg, 
                               "user_id": None, "action": None, "endpoint": None, "latency": None}

            if lvl == "ERROR" or lvl == "WARN":
                pass # Basic message capture is handled by base_pattern
            elif lvl == "INFO":
                # Check for User activity
                u_match = re.match(user_pattern, msg)
                if u_match:
                    entry["user_id"] = u_match.group("uid")
                    entry["action"] = u_match.group("action")
                else:
                    # Check for API activity
                    a_match = re.search(api_pattern, msg)
                    if a_match:
                        entry["endpoint"] = a_match.group("ep")
                        entry["latency"] = int(a_match.group("ms"))
            
            entries.append(entry)
            
    return entries

# --- Transform Phase ---
def calculate_metrics(entries: List[LogEntry]) -> PipelineMetrics:
    """
    Processes raw log entries to compute summaries for the report and DB.
    
    Args:
        entries: List of structured log entries.
        
    Returns:
        A PipelineMetrics object containing error counts, latencies, and session count.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_users = set()

    for e in entries:
        # Error counting
        if e["level"] == "ERROR":
            msg = e["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
            
        # API Latency grouping
        if e["endpoint"] and e["latency"] is not None:
            api_latencies.setdefault(e["endpoint"], []).append(e["latency"])
            
        # Session tracking
        if e["user_id"] and e["action"]:
            if "logged in" in e["action"]:
                active_users.add(e["user_id"])
            elif "logged out" in e["action"]:
                active_users.discard(e["user_id"])

    return {
        "error_counts": error_counts,
        "api_latencies": api_latencies,
        "active_sessions": len(active_users)
    }

# --- Load Phase ---
def save_to_db(metrics: PipelineMetrics) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        metrics: The calculated metrics to store.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Parameterized inserts for errors
        for msg, count in metrics["error_counts"].items():
            cursor.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))

        # Parameterized inserts for API metrics
        for ep, latencies in metrics["api_latencies"].items():
            avg = sum(latencies) / len(latencies)
            cursor.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()

def generate_html_report(metrics: PipelineMetrics) -> None:
    """
    Generates the final HTML report based on calculated metrics.
    
    Args:
        metrics: The calculated metrics.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics["error_counts"].items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, latencies in metrics["api_latencies"].items():
        avg = sum(latencies) / len(latencies)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{metrics['active_sessions']} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

# --- Main Pipeline ---
def run_pipeline() -> None:
    """
    Orchestrates the Extract, Transform, and Load process for server log analysis.
    """
    # Extract
    entries = parse_logs(LOG_FILE)
    
    # Transform
    metrics = calculate_metrics(entries)
    
    # Load
    save_to_db(metrics)
    generate_html_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy logs if none exist for demonstration purposes (matching original script)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
