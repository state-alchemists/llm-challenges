import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# Configuration via Environment Variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex Patterns for Log Parsing
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
class PipelineResult:
    errors: Dict[str, int] = field(default_factory=dict)
    api_metrics: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the log file and extracts structured log entries.
    
    Args:
        file_path: Path to the server log file.
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            match = LOG_PATTERN.match(line.strip())
            if match:
                ts, lvl, msg = match.groups()
                entries.append(LogEntry(ts, lvl, msg))
    return entries

def transform_logs(entries: List[LogEntry]) -> PipelineResult:
    """
    Transforms raw log entries into aggregated metrics.
    
    Args:
        entries: List of parsed LogEntry objects.
    Returns:
        A PipelineResult containing aggregated errors, API metrics, and active sessions.
    """
    result = PipelineResult()
    
    for entry in entries:
        if entry.level == "ERROR":
            result.errors[entry.message] = result.errors.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            # Check for User activity
            user_match = USER_PATTERN.search(entry.message)
            if user_match:
                uid, action = user_match.groups()
                if action == "logged in":
                    result.active_sessions.add(uid)
                elif action == "logged out":
                    result.active_sessions.discard(uid)
            
            # Check for API activity
            api_match = API_PATTERN.search(entry.message)
            if api_match:
                endpoint, latency = api_match.groups()
                result.api_metrics.setdefault(endpoint, []).append(int(latency))
                
        # WARN is processed but not explicitly aggregated for the report in original logic
        # but we keep it in the extract phase.
        
    return result

def load_to_db(result: PipelineResult) -> None:
    """
    Persists aggregated metrics to the SQLite database using parameterized queries.
    
    Args:
        result: The transformed PipelineResult to persist.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Parameterized insert for errors
        error_data = [(now, msg, count) for msg, count in result.errors.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Parameterized insert for API metrics
        api_data = []
        for ep, times in result.api_metrics.items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(result: PipelineResult, output_path: str = "report.html") -> None:
    """
    Generates an HTML report based on the processed metrics.
    
    Args:
        result: The transformed PipelineResult.
        output_path: Destination path for the HTML file.
    """
    html = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>"
    ]
    
    for msg, count in result.errors.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    
    html.append("</ul>")
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    
    for ep, times in result.api_metrics.items():
        avg = sum(times) / len(times) if times else 0
        html.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
        
    html.append("</table>")
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(result.active_sessions)} user(s) currently active</p>")
    html.append("</body>")
    html.append("</html>")
    
    with open(output_path, "w") as f:
        f.write("\n".join(html))

def run_pipeline():
    """
    Main execution pipeline: Extract -> Transform -> Load -> Report.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    result = transform_logs(entries)
    
    # Load
    load_to_db(result)
    
    # Report
    generate_report(result)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Seed log file if it doesn't exist (for local testing/demo)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            
    run_pipeline()
