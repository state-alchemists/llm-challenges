import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# --- Configuration ---
# Use environment variables with sensible defaults for local development
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
    active_sessions: set = field(default_factory=set)

def parse_logs(file_path: str) -> PipelineData:
    """
    Parses the server log file using regex to extract errors, API metrics, and session data.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A PipelineData object containing extracted information.
    """
    data = PipelineData()
    
    # Regex patterns for different log types
    # Generic pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
    # API pattern: API /endpoint took Xms
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")
    # User pattern: User ID action
    user_pattern = re.compile(r"User (\S+) (.+)")

    if not os.path.exists(file_path):
        return data

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            match = log_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, message = match.groups()

            if level == "ERROR":
                data.errors.append(LogEntry(timestamp, level, message))
            
            elif level == "WARN":
                data.errors.append(LogEntry(timestamp, level, message)) # Treated as reportable entries

            elif level == "INFO":
                # Handle API calls
                api_match = api_pattern.search(message)
                if api_match:
                    endpoint, duration = api_match.groups()
                    data.api_calls.append({
                        "timestamp": timestamp,
                        "endpoint": endpoint,
                        "ms": int(duration)
                    })
                    continue

                # Handle User sessions
                user_match = user_pattern.search(message)
                if user_match:
                    uid, action = user_match.groups()
                    if "logged in" in action:
                        data.active_sessions.add(uid)
                    elif "logged out" in action:
                        data.active_sessions.discard(uid)

    return data

def load_to_db(data: PipelineData) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Processes extracted data and loads metrics into the SQLite database.
    
    Args:
        data: The parsed log data.
        
    Returns:
        A tuple containing:
        - error_counts: Mapping of error messages to their frequency.
        - endpoint_stats: Mapping of endpoints to lists of response times.
    """
    # 1. Calculate Error Frequencies
    error_counts = {}
    for entry in data.errors:
        if entry.level == "ERROR":
            msg = entry.message
            error_counts[msg] = error_counts.get(msg, 0) + 1

    # 2. Calculate API Latencies
    endpoint_stats = {}
    for call in data.api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    # 3. Database Persistence
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        # Parameterized queries to prevent SQL Injection
        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count)
            )

        for ep, times in endpoint_stats.items():
            avg = sum(times) / len(times) if times else 0
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg)
            )
        
        conn.commit()

    return error_counts, endpoint_stats

def generate_report(error_counts: Dict[str, int], endpoint_stats: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates an HTML report based on the processed metrics.
    
    Args:
        error_counts: Mapping of error messages to frequency.
        endpoint_stats: Mapping of endpoints to latency lists.
        session_count: Number of active user sessions.
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
    
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{session_count} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")

    with open("report.html", "w") as f:
        f.write("\n".join(html))

def run_pipeline() -> None:
    """
    Main entry point for the log processing pipeline.
    Coordinates the Extract, Transform, and Load phases.
    """
    # Extract
    data = parse_logs(LOG_FILE)
    
    # Transform & Load
    error_counts, endpoint_stats = load_to_db(data)
    
    # Report
    generate_report(error_counts, endpoint_stats, len(data.active_sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create dummy log if not exists for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
