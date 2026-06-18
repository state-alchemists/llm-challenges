import os
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
# Loaded from environment variables with provided defaults
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
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PipelineData:
    errors: List[LogEntry] = field(default_factory=list)
    api_calls: List[Dict[str, Any]] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)

def extract_logs(file_path: str) -> PipelineData:
    """
    Parses the server log file using regex and extracts relevant events.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A PipelineData object containing extracted errors, API calls, and session state.
    """
    data = PipelineData()
    
    # Regex patterns for different log types
    # Expected format: YYYY-MM-DD HH:MM:SS LEVEL Message...
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"User (\w+) (logged in|logged out)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            ts, lvl, msg = match.groups()

            if lvl == "ERROR":
                data.errors.append(LogEntry(ts, lvl, msg))
            
            elif lvl == "WARN":
                data.errors.append(LogEntry(ts, lvl, msg)) # Kept for consistency with original logic

            elif lvl == "INFO":
                # Check for User events
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    if action == "logged in":
                        data.active_sessions[uid] = ts
                    elif action == "logged out":
                        data.active_sessions.pop(uid, None)
                    continue

                # Check for API events
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint, duration = api_match.groups()
                    data.api_calls.append({
                        "timestamp": ts,
                        "endpoint": endpoint,
                        "ms": int(duration)
                    })
    
    return data

def transform_data(data: PipelineData) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Aggregates raw log entries into summaries for reporting and DB storage.
    
    Args:
        data: The raw PipelineData extracted from logs.
        
    Returns:
        A tuple containing:
        1. Error summary: Mapping of error message to occurrence count.
        2. API stats: Mapping of endpoint to list of latencies.
    """
    error_counts: Dict[str, int] = {}
    for err in data.errors:
        # Original code treated WARN as general data but only aggregated ERROR for the summary
        # Looking at the original logic: 'if x["t"] == "ERR":'
        # We only aggregate ERROR levels for the error report summary.
        if err.level == "ERROR":
            error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_stats: Dict[str, List[int]] = {}
    for call in data.api_calls:
        ep = call["endpoint"]
        api_stats.setdefault(ep, []).append(call["ms"])
        
    return error_counts, api_stats

def load_to_db(error_counts: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        error_counts: Summary of errors.
        api_stats: Summary of API latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized insertion for errors
        error_data = [(now, msg, count) for msg, count in error_counts.items()]
        c.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Parameterized insertion for API metrics
        api_data = []
        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        c.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, List[int]], active_session_count: int) -> None:
    """
    Generates the final HTML report.
    
    Args:
        error_counts: Summary of errors.
        api_stats: Summary of API latencies.
        active_session_count: Number of currently active users.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Main orchestration function for the pipeline: Extract -> Transform -> Load.
    """
    # 1. Extract
    data = extract_logs(LOG_FILE)
    
    # 2. Transform
    error_counts, api_stats = transform_data(data)
    
    # 3. Load (DB)
    load_to_db(error_counts, api_stats)
    
    # 4. Load (Report)
    generate_report(error_counts, api_stats, len(data.active_sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock log creation for demonstration/testing as per original script
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
