import datetime
import os
import re
import sqlite3
from typing import Dict, List, NamedTuple, Optional, Any

# --- Configuration ---
# Use environment variables with sensible defaults for local development
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Models ---
class LogEntry(NamedTuple):
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency: Optional[int] = None

# --- Regex Patterns ---
# Sample Log: 2024-01-01 12:00:00 INFO User 42 logged in
# Sample Log: 2024-01-01 12:05:00 ERROR Database timeout
# Sample Log: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s"
    r"(?P<level>INFO|ERROR|WARN)\s"
    r"(?P<message>.*)$"
)
USER_PATTERN = re.compile(r"User\s(?P<uid>\S+)\s(?P<action>.*)$")
API_PATTERN = re.compile(r"API\s(?P<endpoint>\S+)\stook\s(?P<latency>\d+)ms$")

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the log file using regex and extracts structured LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            match = LOG_PATTERN.match(line)
            if not match:
                continue
            
            data = match.groupdict()
            msg = data["message"]
            level = data["level"]
            timestamp = data["timestamp"]

            if level == "INFO":
                # Check for User activity
                user_match = USER_PATTERN.match(msg)
                if user_match:
                    u_data = user_match.groupdict()
                    entries.append(LogEntry(timestamp, level, msg, user_id=u_data["uid"], action=u_data["action"]))
                    continue
                
                # Check for API activity
                api_match = API_PATTERN.match(msg)
                if api_match:
                    a_data = api_match.groupdict()
                    entries.append(LogEntry(timestamp, level, msg, endpoint=a_data["endpoint"], latency=int(a_data["latency"])))
                    continue

            entries.append(LogEntry(timestamp, level, msg))
    
    return entries

def transform_metrics(entries: List[LogEntry]) -> Dict[str, Any]:
    """
    Processes raw log entries into aggregated metrics for DB and Reports.
    """
    error_summary: Dict[str, int] = {}
    api_stats: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for e in entries:
        if e.level == "ERROR":
            error_summary[e.message] = error_summary.get(e.message, 0) + 1
        
        elif e.level == "INFO" and e.user_id:
            if "logged in" in e.action:
                active_sessions[e.user_id] = e.timestamp
            elif "logged out" in e.action:
                active_sessions.pop(e.user_id, None)
        
        elif e.level == "INFO" and e.endpoint and e.latency is not None:
            api_stats.setdefault(e.endpoint, []).append(e.latency)

    return {
        "errors": error_summary,
        "api_metrics": api_stats,
        "sessions": active_sessions
    }

def load_to_db(metrics: Dict[str, Any]) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        for msg, count in metrics["errors"].items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, latencies in metrics["api_metrics"].items():
            avg = sum(latencies) / len(latencies)
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))

        conn.commit()

def generate_report(metrics: Dict[str, Any], output_path: str = "report.html") -> None:
    """
    Generates the final HTML report from the processed metrics.
    """
    errors = metrics["errors"]
    api_stats = metrics["api_metrics"]
    sessions = metrics["sessions"]

    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in errors.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, times in api_stats.items():
        avg = sum(times) / len(times)
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(sessions)} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main orchestration logic: Extract -> Transform -> Load -> Report.
    """
    # 1. Extract
    entries = extract_logs(LOG_FILE)
    
    # 2. Transform
    metrics = transform_metrics(entries)
    
    # 3. Load
    load_to_db(metrics)
    
    # 4. Report
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock data creation if log file doesn't exist (retained from original)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
