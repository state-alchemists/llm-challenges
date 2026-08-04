import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

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
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

@dataclass
class PipelineMetrics:
    errors: Dict[str, int] = field(default_factory=dict)
    api_stats: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def parse_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex.
    
    Expected formats:
    - 2024-01-01 12:00:00 INFO User 42 logged in
    - 2024-01-01 12:05:00 ERROR Database timeout
    - 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    - 2024-01-01 12:09:00 WARN Memory usage at 87%
    """
    entries = []
    # Regex to capture: timestamp (date time), level, and the rest of the message
    # Pattern: ^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    
    # Specific patterns for detail extraction
    user_pattern = re.compile(r"User (\w+) (.+)$")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue
            
            ts, level, msg = match.groups()
            entry = LogEntry(timestamp=ts, level=level, message=msg)

            if level == "INFO":
                # User action check
                user_match = user_pattern.match(msg)
                if user_match:
                    entry.user_id, entry.action = user_match.groups()
                
                # API call check
                api_match = api_pattern.search(msg)
                if api_match:
                    entry.endpoint, lat = api_match.groups()
                    entry.latency_ms = int(lat)

            entries.append(entry)
    return entries

def transform_data(entries: List[LogEntry]) -> PipelineMetrics:
    """
    Transforms raw log entries into aggregated metrics.
    """
    metrics = PipelineMetrics()
    
    for entry in entries:
        if entry.level == "ERROR" or entry.level == "WARN":
            # Original logic grouped ERRORs and WARNs into the error summary
            # Original code: if lvl == "ERROR" -> d_list.append("ERR"); if lvl == "WARN" -> d_list.append("WARN")
            # Then in summary: if x["t"] == "ERR" -> r[msg] = count
            # Note: Original code actually only added "ERR" to the final summary report, 
            # but "WARN" was parsed into d_list. Let's mirror the summary behavior.
            if entry.level == "ERROR":
                metrics.errors[entry.message] = metrics.errors.get(entry.message, 0) + 1

        elif entry.level == "INFO":
            # Session tracking
            if entry.user_id and entry.action:
                if "logged in" in entry.action:
                    metrics.active_sessions.add(entry.user_id)
                elif "logged out" in entry.action:
                    metrics.active_sessions.discard(entry.user_id)
            
            # API Latency tracking
            if entry.endpoint and entry.latency_ms is not None:
                metrics.api_stats.setdefault(entry.endpoint, []).append(entry.latency_ms)
                
    return metrics

def load_to_db(metrics: PipelineMetrics) -> None:
    """
    Loads aggregated metrics into the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load errors
        for msg, count in metrics.errors.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))
            
        # Load API metrics
        for ep, times in metrics.api_stats.items():
            avg = sum(times) / len(times)
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
            
        conn.commit()

def generate_report(metrics: PipelineMetrics, output_path: str = "report.html") -> None:
    """
    Generates the HTML report from the aggregated metrics.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"
    
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics.api_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"
    
    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(metrics.active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    
    with open(output_path, "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Main orchestration function following Extract -> Transform -> Load.
    """
    # Extract
    entries = parse_logs(LOG_FILE)
    
    # Transform
    metrics = transform_data(entries)
    
    # Load
    load_to_db(metrics)
    
    # Report
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy log for testing if it doesn't exist (mirroring original)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
