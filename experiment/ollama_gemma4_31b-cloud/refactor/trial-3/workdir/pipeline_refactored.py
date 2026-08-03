import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TypedDict

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex patterns for log parsing
# Format: YYYY-MM-DD HH:MM:SS LEVEL Message
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
USER_LOGIN_PATTERN = re.compile(r"User (\S+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (\S+) logged out")
API_CALL_PATTERN = re.compile(r"API (\S+) took (\d+)ms")

@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str

@dataclass
class PipelineMetrics:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file and extracts structured log entries.
    
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
            match = LOG_PATTERN.match(line.strip())
            if match:
                timestamp, level, message = match.groups()
                entries.append(LogEntry(timestamp, level, message))
    return entries

def transform_logs(entries: List[LogEntry]) -> PipelineMetrics:
    """
    Processes raw log entries to calculate metrics: error counts, API latencies, and active sessions.
    
    Args:
        entries: A list of parsed LogEntry objects.
        
    Returns:
        A PipelineMetrics object containing the aggregated data.
    """
    metrics = PipelineMetrics()
    
    for entry in entries:
        if entry.level == "ERROR":
            metrics.error_counts[entry.message] = metrics.error_counts.get(entry.message, 0) + 1
        
        elif entry.level == "INFO":
            # Check for User activity
            login_match = USER_LOGIN_PATTERN.search(entry.message)
            if login_match:
                user_id = login_match.group(1)
                metrics.active_sessions.add(user_id)
                continue
                
            logout_match = USER_LOGOUT_PATTERN.search(entry.message)
            if logout_match:
                user_id = logout_match.group(1)
                metrics.active_sessions.discard(user_id)
                continue
            
            # Check for API calls
            api_match = API_CALL_PATTERN.search(entry.message)
            if api_match:
                endpoint, latency = api_match.groups()
                metrics.api_latencies.setdefault(endpoint, []).append(int(latency))
        
        elif entry.level == "WARN":
            # Based on original code, WARN entries were added to d_list but not used in report/DB.
            # Keeping it consistent with the output requirements.
            pass
            
    return metrics

def load_to_db(metrics: PipelineMetrics) -> None:
    """
    Saves processed metrics to the SQLite database using parameterized queries.
    
    Args:
        metrics: The aggregated metrics to store.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        
        now = datetime.datetime.now().isoformat()
        
        # Insert error counts
        error_data = [(now, msg, count) for msg, count in metrics.error_counts.items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)
        
        # Insert API metrics
        api_data = []
        for endpoint, latencies in metrics.api_latencies.items():
            avg = sum(latencies) / len(latencies)
            api_data.append((now, endpoint, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: PipelineMetrics, output_path: str = "report.html") -> None:
    """
    Generates an HTML report summary based on the pipeline metrics.
    
    Args:
        metrics: The aggregated metrics.
        output_path: Path where the HTML report will be saved.
    """
    html = ["<html>", "<head><title>System Report</title></head>", "<body>"]
    
    # Error Summary
    html.append("<h1>Error Summary</h1>")
    html.append("<ul>")
    for msg, count in metrics.error_counts.items():
        html.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    html.append("</ul>")
    
    # API Latency
    html.append("<h2>API Latency</h2>")
    html.append("<table border='1'>")
    html.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, latencies in metrics.api_latencies.items():
        avg = sum(latencies) / len(latencies)
        html.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    html.append("</table>")
    
    # Active Sessions
    html.append("<h2>Active Sessions</h2>")
    html.append(f"<p>{len(metrics.active_sessions)} user(s) currently active</p>")
    
    html.append("</body>")
    html.append("</html>")
    
    # Join blocks with newline for readability matching original
    report_content = "\n".join(["".join(chunk) if isinstance(chunk, list) else chunk for chunk in html])
    # Wait, a simpler way to join the lists correctly:
    final_html = "\n".join(html)
    
    with open(output_path, "w") as f:
        f.write(final_html)

def run_pipeline() -> None:
    """
    Main execution flow for the log processing pipeline: Extract -> Transform -> Load.
    """
    # 1. Extract
    entries = extract_logs(LOG_FILE)
    
    # 2. Transform
    metrics = transform_logs(entries)
    
    # 3. Load (DB + Report)
    load_to_db(metrics)
    generate_report(metrics)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Seed log file if it doesn't exist for testing (original behavior)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
