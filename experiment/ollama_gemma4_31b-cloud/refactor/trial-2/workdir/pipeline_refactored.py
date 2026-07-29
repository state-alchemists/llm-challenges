import os
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Reads server logs and parses them into LogEntry objects using regex.
    
    Args:
        file_path: Path to the log file.
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    # Patterns for the three main log types
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$')
    user_pattern = re.compile(r'User (\S+) (.*)$')
    api_pattern = re.compile(r'API (\S+) took (\d+)ms')

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = base_pattern.match(line)
            if not match:
                continue
            
            dt, lvl, msg = match.groups()
            entry = LogEntry(timestamp=dt, level=lvl, message=msg)

            if lvl == "INFO":
                # Check for User events
                user_match = user_pattern.match(msg)
                if user_match:
                    uid, action = user_match.groups()
                    entry.metadata = {"type": "USER", "uid": uid, "action": action}
                else:
                    # Check for API events
                    api_match = api_pattern.match(msg)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        entry.metadata = {"type": "API", "endpoint": endpoint, "ms": int(duration)}
            elif lvl == "ERROR":
                entry.metadata = {"type": "ERR"}
            elif lvl == "WARN":
                entry.metadata = {"type": "WARN"}
            
            entries.append(entry)
            
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries into summaries for the report and DB.
    
    Args:
        entries: List of parsed LogEntry objects.
    Returns:
        A tuple containing (error_counts, api_latencies, active_sessions_count).
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: set = set()

    for entry in entries:
        meta = entry.metadata
        if meta.get("type") == "ERR":
            msg = entry.message
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        elif meta.get("type") == "API":
            ep = meta["endpoint"]
            api_latencies.setdefault(ep, []).append(meta["ms"])
            
        elif meta.get("type") == "USER":
            uid = meta["uid"]
            action = meta["action"]
            if "logged in" in action:
                active_sessions.add(uid)
            elif "logged out" in action:
                active_sessions.discard(uid)

    return error_counts, api_latencies, len(active_sessions)

def load_to_db(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists the aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error messages to their frequency.
        api_latencies: Map of endpoints to a list of their response times.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Parameterized insertion for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Parameterized insertion for API metrics
        api_data = []
        for ep, times in api_latencies.items():
            avg = sum(times) / len(times)
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report based on the processed metrics.
    
    Args:
        error_counts: Map of error messages to their frequency.
        api_latencies: Map of endpoints to a list of their response times.
        session_count: Number of currently active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def main() -> None:
    """
    Orchestrates the ETL pipeline: Extract -> Transform -> Load -> Report.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_latencies, session_count = transform_logs(entries)
    
    # Load
    load_to_db(error_counts, api_latencies)
    
    # Report
    generate_report(error_counts, api_latencies, session_count)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Maintain the original side-effect of creating a dummy log file if missing for testing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
