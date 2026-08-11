import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# Configuration via Environment Variables
DB_PATH = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE = os.getenv("PIPELINE_LOG_FILE", "server.log")
# These are provided for compatibility with the original script's print statements
# but should be managed via environment variables in a real production environment.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    entry_type: str  # 'ERR', 'USR', 'API', 'WARN'
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Reads the log file and parses lines using regex.
    
    Args:
        file_path: Path to the server log file.
        
    Returns:
        A list of parsed LogEntry objects.
    """
    entries = []
    # Regex patterns
    # Basic line: YYYY-MM-DD HH:MM:SS LEVEL Message
    line_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$')
    # User patterns: User <id> <action>
    user_pattern = re.compile(r'User (\S+) (.*)$')
    # API patterns: API <endpoint> took <ms>ms
    api_pattern = re.compile(r'API (\S+) took (\d+)ms')

    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = line_pattern.match(line)
            if not match:
                continue
                
            dt, lvl, msg = match.groups()
            
            if lvl == "ERROR":
                entries.append(LogEntry(dt, lvl, msg, "ERR"))
            elif lvl == "WARN":
                entries.append(LogEntry(dt, lvl, msg, "WARN"))
            elif lvl == "INFO":
                # Check for User activity
                user_match = user_pattern.search(msg)
                if user_match:
                    uid, action = user_match.groups()
                    entries.append(LogEntry(dt, lvl, msg, "USR", user_id=uid, action=action))
                else:
                    # Check for API activity
                    api_match = api_pattern.search(msg)
                    if api_match:
                        endpoint, ms = api_match.groups()
                        entries.append(LogEntry(dt, lvl, msg, "API", endpoint=endpoint, latency_ms=int(ms)))
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Processes raw log entries into summaries for the report.
    
    Args:
        entries: List of parsed LogEntry objects.
        
    Returns:
        A tuple containing:
        - error_counts: Dict mapping error message to frequency.
        - api_stats: Dict mapping endpoint to list of latencies.
        - active_sessions: Count of users currently logged in.
    """
    error_counts = {}
    api_stats = {}
    sessions = set()

    for entry in entries:
        if entry.entry_type == "ERR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        
        elif entry.entry_type == "API" and entry.endpoint and entry.latency_ms is not None:
            api_stats.setdefault(entry.endpoint, []).append(entry.latency_ms)
            
        elif entry.entry_type == "USR" and entry.user_id and entry.action:
            if "logged in" in entry.action:
                sessions.add(entry.user_id)
            elif "logged out" in entry.action:
                sessions.discard(entry.user_id)

    return error_counts, api_stats, len(sessions)

def load_to_db(error_counts: Dict[str, int], api_stats: Dict[str, List[int]]) -> None:
    """
    Loads summarized metrics into the SQLite database using parameterized queries.
    
    Args:
        error_counts: Error summary data.
        api_stats: API latency data.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Load errors
        for msg, count in error_counts.items():
            c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))
            
        # Load API metrics
        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))
            
        conn.commit()
    finally:
        conn.close()

def generate_report(error_counts: Dict[str, int], api_stats: Dict[str, List[int]], session_count: int, output_path: str = "report.html") -> None:
    """
    Generates an HTML report based on the processed metrics.
    
    Args:
        error_counts: Error summary data.
        api_stats: API latency data.
        session_count: Number of active sessions.
        output_path: Path to the resulting HTML file.
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
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """Main entry point for the log processing pipeline."""
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    error_counts, api_stats, session_count = transform_logs(entries)
    
    # Load
    load_to_db(error_counts, api_stats)
    
    # Report
    generate_report(error_counts, api_stats, session_count)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure a log file exists for demonstration purposes (matching original script)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
