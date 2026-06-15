import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
# Use environment variables with safe defaults for development
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

@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    latency_ms: int

@dataclass
class UserSession:
    user_id: str
    timestamp: str
    action: str  # "logged in" or "logged out"

# --- Regex Patterns ---
# Expected format: YYYY-MM-DD HH:MM:SS LEVEL message...
LOG_PATTERN = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>INFO|ERROR|WARN) (?P<msg>.*)$")
USER_PATTERN = re.compile(r"User (?P<uid>\S+) (?P<action>logged in|logged out)")
API_PATTERN = re.compile(r"API (?P<ep>\S+) took (?P<ms>\d+)ms")

def extract_logs(path: str) -> Tuple[List[LogEntry], List[ApiCall], List[UserSession]]:
    """
    Parses the log file and extracts structured entries.
    
    Args:
        path: Path to the log file.
        
    Returns:
        A tuple containing lists of errors/warnings, API calls, and user sessions.
    """
    errors: List[LogEntry] = []
    api_calls: List[ApiCall] = []
    sessions: List[UserSession] = []

    if not os.path.exists(path):
        return errors, api_calls, sessions

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            ts, lvl, msg = match.group("ts"), match.group("lvl"), match.group("msg")

            if lvl == "ERROR" or lvl == "WARN":
                errors.append(LogEntry(ts, lvl, msg))
            
            elif lvl == "INFO":
                # Check for User events
                user_match = USER_PATTERN.search(msg)
                if user_match:
                    sessions.append(UserSession(
                        user_id=user_match.group("uid"),
                        timestamp=ts,
                        action=user_match.group("action")
                    ))
                    continue
                
                # Check for API events
                api_match = API_PATTERN.search(msg)
                if api_match:
                    api_calls.append(ApiCall(
                        timestamp=ts,
                        endpoint=api_match.group("ep"),
                        latency_ms=int(api_match.group("ms"))
                    ))

    return errors, api_calls, sessions

def transform_log_data(
    errors: List[LogEntry], 
    api_calls: List[ApiCall], 
    sessions: List[UserSession]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Aggregates raw log entries into summary statistics.
    
    Args:
        errors: List of filtered error/warn entries.
        api_calls: List of extracted API calls.
        sessions: List of extracted user sessions.
        
    Returns:
        A tuple containing:
        1. Error counts map {message: count}
        2. API latency map {endpoint: [latencies]}
        3. Final active session count
    """
    # Error aggregation (only ERROR level as per original logic for the report)
    error_counts: Dict[str, int] = {}
    for e in errors:
        if e.level == "ERROR":
            error_counts[e.message] = error_counts.get(e.message, 0) + 1

    # API latency aggregation
    api_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        api_stats.setdefault(call.endpoint, []).append(call.latency_ms)

    # Session tracking
    active_users = set()
    for s in sessions:
        if s.action == "logged in":
            active_users.add(s.user_id)
        elif s.action == "logged out":
            active_users.discard(s.user_id)

    return error_counts, api_stats, len(active_users)

def load_to_db(error_counts: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error messages to counts.
        api_stats: Map of endpoints to list of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Parameterized inserts for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Parameterized inserts for API metrics
        api_data = []
        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, List[int]], active_sessions: int) -> None:
    """
    Generates the final HTML report from aggregated data.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    html.append("<h1>Error Summary</h1>\n<ul>")
    for msg, count in error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    html.append("</ul>")

    html.append("<h2>API Latency</h2>\n<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in api_stats.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    html.append("</table>")

    html.append(f"<h2>Active Sessions</h2>\n<p>{active_sessions} user(s) currently active</p>")
    html.append("</body>\n</html>")

    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """Main orchestration function for the log processing pipeline."""
    # Extract
    errors, api_calls, sessions = extract_logs(LOG_FILE)
    
    # Transform
    err_counts, api_stats, active_count = transform_log_data(errors, api_calls, sessions)
    
    # Load
    load_to_db(err_counts, api_stats)
    
    # Report
    generate_report(err_counts, api_stats, active_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup mock log for testing if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
