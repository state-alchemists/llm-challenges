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
DB_PASS = os.getenv("DB_PASS", "password123")

# Log parsing regex patterns
# Example: 2024-01-01 12:00:00 INFO User 42 logged in
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
USER_PATTERN = re.compile(r"User (\S+) (.*)$")
API_PATTERN = re.compile(r"API (\S+)(?: took (\d+)ms)?$")

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
    duration_ms: int

@dataclass
class ExtractionResult:
    errors: List[LogEntry] = field(default_factory=list)
    user_actions: List[UserAction] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)

def extract_logs(file_path: str) -> ExtractionResult:
    """
    Parses the server log file using regex and categorizes entries.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        ExtractionResult containing categorized parsed data.
    """
    result = ExtractionResult()
    
    if not os.path.exists(file_path):
        return result

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = LOG_PATTERN.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            
            if level == "ERROR":
                result.errors.append(LogEntry(timestamp, level, content))
            elif level == "WARN":
                result.warnings.append(LogEntry(timestamp, level, content))
            elif level == "INFO":
                # Check for User action
                user_match = USER_PATTERN.match(content)
                if user_match:
                    user_id, action = user_match.groups()
                    result.user_actions.append(UserAction(timestamp, user_id, action))
                    continue
                
                # Check for API call
                api_match = API_PATTERN.match(content)
                if api_match:
                    endpoint, duration = api_match.groups()
                    result.api_calls.append(ApiCall(
                        timestamp, 
                        endpoint, 
                        int(duration) if duration else 0
                    ))
                    
    return result

def transform_data(data: ExtractionResult) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Aggregates raw extracted data into metrics for reporting and loading.
    
    Args:
        data: The raw ExtractionResult.
        
    Returns:
        A tuple containing:
        - error_summary: Dict of error message -> count
        - api_stats: Dict of endpoint -> list of durations
        - active_sessions: Count of users who logged in but didn't log out
    """
    # Error summary
    error_summary: Dict[str, int] = {}
    for err in data.errors:
        error_summary[err.message] = error_summary.get(err.message, 0) + 1
        
    # API stats
    api_stats: Dict[str, List[int]] = {}
    for call in data.api_calls:
        api_stats.setdefault(call.endpoint, []).append(call.duration_ms)
        
    # Active sessions tracking
    sessions = set()
    for ua in data.user_actions:
        if "logged in" in ua.action:
            sessions.add(ua.user_id)
        elif "logged out" in ua.action:
            sessions.discard(ua.user_id)
            
    return error_summary, api_stats, len(sessions)

def load_to_db(error_summary: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Loads aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_summary: Aggregated error counts.
        api_stats: API endpoint latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Parameterized inserts for errors
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Parameterized inserts for API metrics
        api_data = []
        for ep, durations in api_stats.items():
            avg = sum(durations) / len(durations) if durations else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_summary: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report file.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    # Error Summary
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_summary.items():
        out += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"
    
    # API Latency
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, durations in api_stats.items():
        avg = sum(durations) / len(durations) if durations else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"
    
    # Active Sessions
    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    
    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """Main execution flow: Extract -> Transform -> Load/Report."""
    # 1. Extract
    extracted_data = extract_logs(LOG_FILE)
    
    # 2. Transform
    error_summary, api_stats, session_count = transform_data(extracted_data)
    
    # 3. Load
    load_to_db(error_summary, api_stats)
    
    # 4. Report
    generate_report(error_summary, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Bootstrap log file for testing if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
