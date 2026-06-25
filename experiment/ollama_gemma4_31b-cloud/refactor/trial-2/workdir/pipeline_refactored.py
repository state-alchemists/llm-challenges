import datetime
import os
import re
import sqlite3
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

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

# Regex patterns for log parsing
# Format: YYYY-MM-DD HH:MM:SS LEVEL Message
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
USER_PATTERN = re.compile(r"User (\S+) (.*)$")
API_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

def extract_logs(file_path: str) -> List[str]:
    """Reads raw lines from the log file."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        return f.readlines()

def transform_logs(lines: List[str]) -> Tuple[List[LogEntry], Dict[str, str], List[LogEntry]]:
    """
    Parses raw log lines into structured data.
    Returns a tuple of (all_entries, active_sessions, api_calls).
    """
    all_entries: List[LogEntry] = []
    sessions: Dict[str, str] = {}
    api_calls: List[LogEntry] = []

    for line in lines:
        line = line.strip()
        match = LOG_PATTERN.match(line)
        if not match:
            continue

        timestamp, level, body = match.groups()
        entry = LogEntry(timestamp=timestamp, level=level, message=body)

        if level == "ERROR":
            all_entries.append(entry)
        elif level == "WARN":
            all_entries.append(entry)
        elif level == "INFO":
            # User logic
            user_match = USER_PATTERN.match(body)
            if user_match:
                uid, action = user_match.groups()
                entry.user_id = uid
                entry.action = action
                if "logged in" in action:
                    sessions[uid] = timestamp
                elif "logged out" in action:
                    sessions.pop(uid, None)
                all_entries.append(entry)
            # API logic
            api_match = API_PATTERN.search(body)
            if api_match:
                endpoint, latency = api_match.groups()
                entry.endpoint = endpoint
                entry.latency_ms = int(latency)
                api_calls.append(entry)

    return all_entries, sessions, api_calls

def load_to_db(errors_counts: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """Loads aggregated metrics into the SQLite database using parameterized queries."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Load errors
        error_data = [(now, msg, count) for msg, count in errors_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Load API metrics
        api_data = [(now, ep, sum(times)/len(times)) for ep, times in api_stats.items()]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(errors_counts: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int) -> str:
    """Generates the HTML report string."""
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in errors_counts.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_stats.items():
        avg = sum(times) / len(times)
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    html += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    html += "</body>\n</html>"
    return html

def run_pipeline() -> None:
    """Main pipeline orchestration."""
    # Extract
    lines = extract_logs(LOG_FILE)
    
    # Transform
    all_entries, sessions, api_calls = transform_logs(lines)
    
    # Aggregate Errors
    error_counts: Dict[str, int] = {}
    for entry in all_entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
            
    # Aggregate API
    api_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        if call.endpoint is not None and call.latency_ms is not None:
            api_stats.setdefault(call.endpoint, []).append(call.latency_ms)

    # Load
    load_to_db(error_counts, api_stats)

    # Report
    report_html = generate_report(error_counts, api_stats, len(sessions))
    with open("report.html", "w") as f:
        f.write(report_html)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy data if log file doesn't exist for verification
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
