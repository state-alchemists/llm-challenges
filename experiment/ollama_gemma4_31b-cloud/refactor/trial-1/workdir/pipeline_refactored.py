import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
# Use environment variables for configuration to avoid hardcoding credentials and paths.
DB_PATH = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE = os.getenv("PIPELINE_LOG_FILE", "server.log")
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

@dataclass
class PipelineData:
    errors: List[LogEntry] = field(default_factory=list)
    api_calls: List[LogEntry] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)

def extract_logs(file_path: str) -> PipelineData:
    """
    Parses the server log file using regex and extracts relevant events.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        PipelineData object containing categorized log entries and session state.
    """
    data = PipelineData()
    
    # Regex patterns for different log levels and formats
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    log_pattern = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>\w+) (?P<msg>.*)$")
    user_pattern = re.compile(r"User (?P<uid>\S+) (?P<action>.*)")
    api_pattern = re.compile(r"API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?")

    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = log_pattern.match(line)
            if not match:
                continue

            ts, lvl, msg = match.group("ts"), match.group("lvl"), match.group("msg")

            if lvl == "ERROR":
                data.errors.append(LogEntry(timestamp=ts, level=lvl, message=msg))
            
            elif lvl == "INFO":
                # Check for User activity
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.group("uid"), user_match.group("action")
                    if "logged in" in action:
                        data.active_sessions[uid] = ts
                    elif "logged out" in action:
                        data.active_sessions.pop(uid, None)
                    # The original code adds USR events to d_list; keeping it for completeness if needed,
                    # though the report only uses session count.
                
                # Check for API activity
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint = api_match.group("endpoint")
                    ms_str = api_match.group("ms")
                    ms = int(ms_str) if ms_str else 0
                    data.api_calls.append(LogEntry(
                        timestamp=ts, level=lvl, message=msg, 
                        endpoint=endpoint, latency_ms=ms
                    ))
            
            elif lvl == "WARN":
                # Original code added WARN to d_list, but report doesn't use it.
                # We store it in errors as a general "issue" or just ignore it based on report requirements.
                # The original report only iterated over 'r' which was populated by 'ERR'.
                pass

    return data

def transform_metrics(data: PipelineData) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Aggregates raw log entries into summaries for the report and database.
    
    Args:
        data: The extracted PipelineData.
        
    Returns:
        A tuple containing (error_counts, api_latency_avgs).
    """
    error_counts = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_stats = {}
    for call in data.api_calls:
        ep = call.endpoint
        if ep not in api_stats:
            api_stats[ep] = []
        api_stats[ep].append(call.latency_ms)

    api_avgs = {ep: sum(times) / len(times) for ep, times in api_stats.items()}
    
    return error_counts, api_avgs

def load_to_db(error_counts: Dict[str, int], api_avgs: Dict[str, float]) -> None:
    """
    Loads the aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_counts: Dictionary of error messages and their counts.
        api_avgs: Dictionary of endpoints and their average latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Parameterized queries to prevent SQL injection
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))
        
        for ep, avg in api_avgs.items():
            cursor.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_avgs: Dict[str, float], session_count: int) -> None:
    """
    Generates the HTML report file.
    
    Args:
        error_counts: Aggregated error data.
        api_avgs: Aggregated API latency data.
        session_count: Number of currently active sessions.
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
    
    for ep, avg in api_avgs.items():
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """Main orchestration function for the log processing pipeline."""
    # 1. Extract
    data = extract_logs(LOG_FILE)
    
    # 2. Transform
    error_counts, api_avgs = transform_metrics(data)
    
    # 3. Load
    load_to_db(error_counts, api_avgs)
    
    # 4. Report
    generate_report(error_counts, api_avgs, len(data.active_sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create dummy log file if it doesn't exist (preserving original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
