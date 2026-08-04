import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, TypedDict, Optional
from dataclasses import dataclass

# --- Configuration ---
# Defaults provided for local development, overridden by environment variables.
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

@dataclass
class ApiCall:
    timestamp: str
    endpoint: str
    latency_ms: int

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

class PipelineData(TypedDict):
    errors: Dict[str, int]
    api_metrics: Dict[str, List[int]]
    active_sessions: int

def parse_logs(log_path: str) -> Tuple[List[LogEntry], List[ApiCall], int]:
    """
    Extracts structured data from server logs using regular expressions.
    
    Returns:
        A tuple containing:
        - List of ERROR logs
        - List of API call metrics
        - Count of active user sessions
    """
    errors: List[LogEntry] = []
    api_calls: List[ApiCall] = []
    sessions: set = set()

    # Regex patterns
    # Example: 2024-01-01 12:00:00 INFO User 42 logged in
    # Example: 2024-01-01 12:05:00 ERROR Database timeout
    # Example: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$')
    user_login_pattern = re.compile(r'User (\w+) logged in')
    user_logout_pattern = re.compile(r'User (\w+) logged out')
    api_pattern = re.compile(r'API (\S+) took (\d+)ms')

    if not os.path.exists(log_path):
        return [], [], 0

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            match = log_pattern.match(line)
            if not match:
                continue

            timestamp, level, message = match.groups()

            if level == "ERROR":
                errors.append(LogEntry(timestamp, level, message))
            elif level == "INFO":
                # Check for User activity
                login_match = user_login_pattern.search(message)
                if login_match:
                    sessions.add(login_match.group(1))
                    continue
                
                logout_match = user_logout_pattern.search(message)
                if logout_match:
                    uid = logout_match.group(1)
                    sessions.discard(uid)
                    continue

                # Check for API activity
                api_match = api_pattern.search(message)
                if api_match:
                    api_calls.append(ApiCall(timestamp, api_match.group(1), int(api_match.group(2))))

    return errors, api_calls, len(sessions)

def transform_data(errors: List[LogEntry], api_calls: List[ApiCall], active_sessions: int) -> PipelineData:
    """
    Transforms raw log entries into aggregated metrics.
    """
    error_summary: Dict[str, int] = {}
    for err in errors:
        error_summary[err.message] = error_summary.get(err.message, 0) + 1

    api_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        api_stats.setdefault(call.endpoint, []).append(call.latency_ms)

    return {
        "errors": error_summary,
        "api_metrics": api_stats,
        "active_sessions": active_sessions
    }

def load_to_db(data: PipelineData) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Load errors
        error_inserts = [
            (now, msg, count) for msg, count in data["errors"].items()
        ]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_inserts)

        # Load API metrics
        api_inserts = [
            (now, ep, sum(times) / len(times)) 
            for ep, times in data["api_metrics"].items()
        ]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_inserts)
        
        conn.commit()

def generate_report(data: PipelineData, output_path: str = "report.html") -> None:
    """
    Generates the HTML report from the transformed data.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    # Error Summary
    html.append("<h1>Error Summary</h1>")
    html.append("<ul>")
    for msg, count in data["errors"].items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    html.append("</ul>")

    # API Latency
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in data["api_metrics"].items():
        avg = sum(times) / len(times)
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    html.append("</table>")

    # Active Sessions
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{data['active_sessions']} user(s) currently active</p>")
    
    html.append("</body>")
    html.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline():
    """
    Main orchestration function implementing the ETL pipeline.
    """
    # Extract
    errors, api_calls, session_count = parse_logs(LOG_FILE)
    
    # Transform
    data = transform_data(errors, api_calls, session_count)
    
    # Load
    load_to_db(data)
    generate_report(data)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure log file exists for demonstration purposes as per original script
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
