import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- Configuration ---
# Use environment variables for all configuration to avoid hardcoding
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
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

# --- Regex Patterns ---
# Format: YYYY-MM-DD HH:MM:SS LEVEL Message
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")
# Specific patterns for INFO lines
USER_LOGIN_PATTERN = re.compile(r"User (\w+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (\w+) logged out")
API_CALL_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the log file and extracts structured data using regex.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            ts, lvl, msg = match.groups()
            entry = LogEntry(timestamp=ts, level=lvl, message=msg)

            if lvl == "INFO":
                # Check for User activity
                login_match = USER_LOGIN_PATTERN.search(msg)
                logout_match = USER_LOGOUT_PATTERN.search(msg)
                api_match = API_CALL_PATTERN.search(msg)

                if login_match:
                    entry.user_id = login_match.group(1)
                    entry.action = "logged in"
                elif logout_match:
                    entry.user_id = logout_match.group(1)
                    entry.action = "logged out"
                elif api_match:
                    entry.endpoint = api_match.group(1)
                    entry.latency_ms = int(api_match.group(2))

            entries.append(entry)
    return entries

def transform_data(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries into aggregates for the report.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A tuple containing:
        - error_counts: Dictionary of {error_message: count}
        - api_stats: Dictionary of {endpoint: [latencies]}
        - active_sessions: Final count of users who logged in but didn't log out.
    """
    error_counts: Dict[str, int] = {}
    api_stats: Dict[str, List[int]] = {}
    sessions = set()

    for e in entries:
        if e.level == "ERROR":
            error_counts[e.message] = error_counts.get(e.message, 0) + 1
        
        elif e.level == "INFO":
            if e.user_id:
                if e.action == "logged in":
                    sessions.add(e.user_id)
                elif e.action == "logged out":
                    sessions.discard(e.user_id)
            
            if e.endpoint and e.latency_ms is not None:
                api_stats.setdefault(e.endpoint, []).append(e.latency_ms)

    return error_counts, api_stats, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Loads aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_counts: Map of error messages to their frequency.
        api_stats: Map of endpoints to their lists of latency measurements.
    """
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized inserts to prevent SQL injection
        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, List[int]], active_sessions: int, output_path: str = "report.html") -> None:
    """
    Generates an HTML report based on the aggregated data.
    
    Args:
        error_counts: Map of error messages to counts.
        api_stats: Map of endpoints to latency lists.
        active_sessions: Number of active user sessions.
        output_path: File path for the resulting HTML.
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
    
    for ep, times in api_stats.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{active_sessions} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main execution flow: Extract -> Transform -> Load.
    """
    print(f"Processing logs from {LOG_FILE}...")
    entries = extract_logs(LOG_FILE)
    
    print("Transforming data...")
    error_counts, api_stats, active_sessions = transform_data(entries)
    
    print(f"Connecting to database at {DB_PATH}...")
    load_to_db(error_counts, api_stats)
    
    print("Generating report...")
    generate_report(error_counts, api_stats, active_sessions)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure dummy log exists for demonstration if not present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
