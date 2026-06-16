import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# --- Configuration ---
# Load from environment variables with defaults for local development
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Regex Patterns ---
# Format: YYYY-MM-DD HH:MM:SS LEVEL Message
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
USER_LOGIN_PATTERN = re.compile(r"User (\w+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (\w+) logged out")
API_CALL_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class ApiMetric:
    timestamp: str
    endpoint: str
    latency: int

def extract_logs(file_path: str) -> Tuple[List[LogEntry], List[ApiMetric], Dict[str, str]]:
    """
    Parses the server log file and extracts structured data.
    
    Returns:
        A tuple containing:
        - List of error/warn entries
        - List of API call metrics
        - Dictionary of active sessions {user_id: login_time}
    """
    errors_and_warns = []
    api_metrics = []
    active_sessions = {}

    if not os.path.exists(file_path):
        return [], [], {}

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = LOG_PATTERN.match(line)
            if not match:
                continue

            dt, lvl, msg = match.groups()

            if lvl == "ERROR" or lvl == "WARN":
                errors_and_warns.append(LogEntry(dt, lvl, msg))
            
            elif lvl == "INFO":
                # Handle User Sessions
                login_match = USER_LOGIN_PATTERN.search(msg)
                if login_match:
                    uid = login_match.group(1)
                    active_sessions[uid] = dt
                    continue
                
                logout_match = USER_LOGOUT_PATTERN.search(msg)
                if logout_match:
                    uid = logout_match.group(1)
                    active_sessions.pop(uid, None)
                    continue

                # Handle API Metrics
                api_match = API_CALL_PATTERN.search(msg)
                if api_match:
                    endpoint, latency = api_match.groups()
                    api_metrics.append(ApiMetric(dt, endpoint, int(latency)))

    return errors_and_warns, api_metrics, active_sessions

def transform_data(errors: List[LogEntry], api_metrics: List[ApiMetric]) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Aggregates raw log entries into summaries for reporting and storage.
    """
    # Error summary: {message: count}
    error_counts = {}
    for entry in errors:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # API stats: {endpoint: avg_latency}
    endpoint_latencies: Dict[str, List[int]] = {}
    for metric in api_metrics:
        endpoint_latencies.setdefault(metric.endpoint, []).append(metric.latency)
    
    avg_latencies = {
        ep: sum(times) / len(times) 
        for ep, times in endpoint_latencies.items() 
        if times
    }

    return error_counts, avg_latencies

def load_to_db(error_counts: Dict[str, int], avg_latencies: Dict[str, float]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Use parameterized queries to prevent SQL injection
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, avg in avg_latencies.items():
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], avg_latencies: Dict[str, float], active_sessions: Dict[str, str]) -> None:
    """
    Generates the HTML report based on the processed data.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, avg in avg_latencies.items():
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open("report.html", "w") as f:
        f.write("\n".join(html))

def main():
    """
    Main pipeline execution flow: Extract -> Transform -> Load -> Report.
    """
    # EXTRACT
    raw_errors, raw_api, sessions = extract_logs(LOG_FILE)
    
    # TRANSFORM
    error_summary, api_summary = transform_data(raw_errors, raw_api)
    
    # LOAD
    load_to_db(error_summary, api_summary)
    
    # REPORT
    generate_report(error_summary, api_summary, sessions)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure a sample log exists for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    main()
