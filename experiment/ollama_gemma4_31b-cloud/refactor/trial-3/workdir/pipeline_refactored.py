import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any
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
    metadata: Dict[str, Any]

# Regex patterns for log parsing
# Expected format: YYYY-MM-DD HH:MM:SS LEVEL Message...
LOG_PATTERN = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>\w+) (?P<msg>.*)$")
USER_LOGIN_PATTERN = re.compile(r"User (?P<uid>\S+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (?P<uid>\S+) logged out")
API_CALL_PATTERN = re.compile(r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms")

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the log file and extracts structured LogEntry objects.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed log entries.
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
            
            ts, lvl, msg = match.group("ts"), match.group("lvl"), match.group("msg")
            metadata = {}

            if lvl == "INFO":
                # Check for User activity
                user_login = USER_LOGIN_PATTERN.search(msg)
                if user_login:
                    metadata["type"] = "USER_LOGIN"
                    metadata["uid"] = user_login.group("uid")
                else:
                    user_logout = USER_LOGOUT_PATTERN.search(msg)
                    if user_logout:
                        metadata["type"] = "USER_LOGOUT"
                        metadata["uid"] = user_logout.group("uid")
                    else:
                        # Check for API call
                        api_match = API_CALL_PATTERN.search(msg)
                        if api_match:
                            metadata["type"] = "API_CALL"
                            metadata["endpoint"] = api_match.group("endpoint")
                            metadata["ms"] = int(api_match.group("ms"))
            
            entries.append(LogEntry(timestamp=ts, level=lvl, message=msg, metadata=metadata))
            
    return entries

def transform_metrics(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Aggregates log entries into error counts, API latencies, and active session count.
    
    Args:
        entries: List of parsed LogEntry objects.
        
    Returns:
        A tuple containing:
        - error_summary: Dict mapping error messages to counts.
        - api_latencies: Dict mapping endpoints to lists of response times.
        - active_sessions: Integer count of users currently logged in.
    """
    error_summary = {}
    api_latencies = {}
    sessions = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            m_type = entry.metadata.get("type")
            if m_type == "USER_LOGIN":
                sessions.add(entry.metadata["uid"])
            elif m_type == "USER_LOGOUT":
                sessions.discard(entry.metadata["uid"])
            elif m_type == "API_CALL":
                ep = entry.metadata["endpoint"]
                api_latencies.setdefault(ep, []).append(entry.metadata["ms"])
                
    return error_summary, api_latencies, len(sessions)

def load_to_db(error_summary: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists the transformed metrics into the SQLite database using parameterized queries.
    
    Args:
        error_summary: Aggregated error counts.
        api_latencies: Aggregated API response times.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load errors
        error_data = [(now, msg, count) for msg, count in error_summary.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Load API metrics
        api_data = [
            (now, ep, sum(times) / len(times)) 
            for ep, times in api_latencies.items()
        ]
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(error_summary: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int, output_path: str = "report.html") -> None:
    """
    Generates the final HTML report.
    
    Args:
        error_summary: Aggregated error counts.
        api_latencies: Aggregated API response times.
        session_count: Count of active sessions.
        output_path: Path to write the report file.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in error_summary.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main execution flow for the log processing pipeline.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_summary, api_latencies, session_count = transform_metrics(entries)
    
    # Load
    load_to_db(error_summary, api_latencies)
    
    # Report
    generate_report(error_summary, api_latencies, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock log file for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
