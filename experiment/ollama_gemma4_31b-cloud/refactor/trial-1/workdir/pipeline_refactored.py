import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# --- Configuration ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
# These aren't used by sqlite3 but kept for logic consistency with original script
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Models ---
@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class UserAction:
    timestamp: str
    user_id: str
    action: str

@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    latency_ms: int

@dataclass
class PipelineData:
    errors: List[LogEntry] = field(default_factory=list)
    user_actions: List[UserAction] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)

# --- Extract ---
def parse_logs(file_path: str) -> PipelineData:
    """
    Parses server logs using regex to extract errors, user actions, and API metrics.
    """
    data = PipelineData()
    active_sessions: Dict[str, str] = {} # Local tracking for session count logic

    # Regex patterns
    # Log format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\S+) (.*)$")
    api_pattern = re.compile(r"API (\S+)(?: took (\d+)ms)?$")

    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            dt, level, msg = match.groups()

            if level == "ERROR":
                data.errors.append(LogEntry(dt, level, msg))
            elif level == "WARN":
                # The original script tracked WARN in d_list but didn't use it for reports or DB
                pass
            elif level == "INFO":
                if "User" in msg:
                    u_match = user_pattern.match(msg)
                    if u_match:
                        uid, action = u_match.groups()
                        data.user_actions.append(UserAction(dt, uid, action))
                elif "API" in msg:
                    a_match = api_pattern.match(msg)
                    if a_match:
                        endpoint, duration = a_match.groups()
                        data.api_calls.append(ApiCall(dt, endpoint, int(duration) if duration else 0))

    return data

def calculate_active_sessions(user_actions: List[UserAction]) -> int:
    """
    Calculates the number of active sessions based on login/logout events.
    """
    sessions = set()
    for action in user_actions:
        if "logged in" in action.action:
            sessions.add(action.user_id)
        elif "logged out" in action.action:
            sessions.discard(action.user_id)
    return len(sessions)

# --- Transform ---
def aggregate_errors(errors: List[LogEntry]) -> Dict[str, int]:
    """Counts occurrences of each unique error message."""
    counts = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts

def aggregate_api_metrics(calls: List[ApiCall]) -> Dict[str, float]:
    """Calculates average latency per endpoint."""
    stats = {}
    latencies = {}
    for call in calls:
        latencies.setdefault(call.endpoint, []).append(call.latency_ms)
    
    for ep, times in latencies.items():
        stats[ep] = sum(times) / len(times)
    return stats

# --- Load ---
def save_to_db(error_counts: Dict[str, int], api_stats: Dict[str, float]) -> None:
    """
    Persists aggregated metrics to SQLite using parameterized queries to prevent SQL injection.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()
        
        # Use parameterized queries (?) instead of string formatting
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        api_data = [(now, ep, avg) for ep, avg in api_stats.items()]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

# --- Report ---
def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, float], session_count: int) -> None:
    """Generates a static HTML report from the processed metrics."""
    
    error_list_html = "".join(
        f"<li><b>{msg}</b>: {count} occurrences</li>\n" 
        for msg, count in error_counts.items()
    )
    
    api_rows_html = "".join(
        f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n" 
        for ep, avg in api_stats.items()
    )

    html = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        f"<h1>Error Summary</h1>\n<ul>\n{error_list_html}</ul>\n"
        f"<h2>API Latency</h2>\n<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        f"{api_rows_html}</table>\n"
        f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
        "</body>\n</html>"
    )

    with open("report.html", "w") as f:
        f.write(html)

# --- Main Pipeline ---
def run_pipeline() -> None:
    """
    Orchestrates the Extract, Transform, Load, and Report process.
    """
    # 1. Extract
    data = parse_logs(LOG_FILE)
    
    # 2. Transform
    error_counts = aggregate_errors(data.errors)
    api_stats = aggregate_api_metrics(data.api_calls)
    session_count = calculate_active_sessions(data.user_actions)
    
    # 3. Load
    save_to_db(error_counts, api_stats)
    
    # 4. Report
    generate_report(error_counts, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup mock data for standalone execution (preserving original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
