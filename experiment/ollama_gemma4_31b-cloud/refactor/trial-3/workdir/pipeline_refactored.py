import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class Config:
    """Configuration loaded from environment variables."""
    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")

# Regex patterns for log parsing
# Format: YYYY-MM-DD HH:MM:SS LEVEL Message
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
USER_PATTERN = re.compile(r"User (\S+) (logged in|logged out)")
API_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    latency: int

def extract_logs(file_path: str) -> Tuple[List[LogEntry], List[ApiCall], Dict[str, str]]:
    """
    Parses the log file and extracts errors, API calls, and tracks active sessions.
    
    Args:
        file_path: Path to the server log file.
        
    Returns:
        A tuple containing:
        - List of general log entries (mostly errors/warns)
        - List of parsed API calls
        - Dictionary of active sessions {user_id: login_time}
    """
    entries: List[LogEntry] = []
    api_calls: List[ApiCall] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(file_path):
        return entries, api_calls, sessions

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            ts, level, msg = match.groups()

            if level == "ERROR" or level == "WARN":
                entries.append(LogEntry(ts, level, msg))
            
            elif level == "INFO":
                # User session tracking
                user_match = USER_PATTERN.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    if action == "logged in":
                        sessions[uid] = ts
                    elif action == "logged out":
                        sessions.pop(uid, None)
                    continue

                # API call tracking
                api_match = API_PATTERN.search(msg)
                if api_match:
                    endpoint, latency = api_match.groups()
                    api_calls.append(ApiCall(ts, endpoint, int(latency)))

    return entries, api_calls, sessions

def transform_data(entries: List[LogEntry], api_calls: List[ApiCall]) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Aggregates log entries and calculates average API latency.
    
    Args:
        entries: List of parsed log entries.
        api_calls: List of parsed API calls.
        
    Returns:
        A tuple containing:
        - Error summary {message: count}
        - API latency stats {endpoint: avg_latency}
    """
    error_summary: Dict[str, int] = {}
    for entry in entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_stats.setdefault(call.endpoint, []).append(call.latency)

    api_averages = {ep: sum(times) / len(times) for ep, times in endpoint_stats.items()}
    
    return error_summary, api_averages

def load_metrics(config: Config, error_summary: Dict[str, int], api_averages: Dict[str, float]) -> None:
    """
    Saves aggregated metrics to the database using parameterized queries.
    
    Args:
        config: Configuration object.
        error_summary: Aggregated error counts.
        api_averages: Calculated API average latencies.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized inserts to prevent SQL injection
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        api_data = [(now, ep, avg) for ep, avg in api_averages.items()]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(output_path: str, error_summary: Dict[str, int], api_averages: Dict[str, float], session_count: int) -> None:
    """
    Produces the final HTML report.
    
    Args:
        output_path: Path to save the HTML file.
        error_summary: Error counts for the summary section.
        api_averages: Average latencies for the table.
        session_count: Number of active sessions.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    html += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_summary.items():
        html += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_averages.items():
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    html += f"<h2>Active Sessions</h2>\n<p>{session_count} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open(output_path, "w") as f:
        f.write(html)

def run_pipeline():
    """Entry point for the log processing pipeline."""
    config = Config()
    
    # Extract
    entries, api_calls, sessions = extract_logs(config.log_file)
    
    # Transform
    error_summary, api_averages = transform_data(entries, api_calls)
    
    # Load
    load_metrics(config, error_summary, api_averages)
    
    # Report
    generate_report("report.html", error_summary, api_averages, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock data for first run if log file doesn't exist
    initial_log = "server.log"
    if not os.path.exists(initial_log):
        with open(initial_log, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
