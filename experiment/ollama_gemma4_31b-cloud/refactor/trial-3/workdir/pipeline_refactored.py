import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, TypedDict, Optional

@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""
    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")

class LogEntry(TypedDict):
    timestamp: str
    level: str
    message: str
    user_id: Optional[str]
    action: Optional[str]
    endpoint: Optional[str]
    latency_ms: Optional[int]

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regular expressions.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of parsed log entries.
    """
    entries = []
    # Pattern: YYYY-MM-DD HH:MM:SS LEVEL Message
    # Examples: 
    # 2024-01-01 12:00:00 INFO User 42 logged in
    # 2024-01-01 12:05:00 ERROR Database timeout
    # 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    line_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")
    user_pattern = re.compile(r"User (\S+) (.*)$")
    api_pattern = re.compile(r"API (\S+)(?: took (\d+)ms)?")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = line_pattern.match(line)
            if not match:
                continue
                
            timestamp, level, content = match.groups()
            entry: LogEntry = {
                "timestamp": timestamp,
                "level": level,
                "message": content,
                "user_id": None,
                "action": None,
                "endpoint": None,
                "latency_ms": None
            }

            if level == "INFO":
                user_match = user_pattern.match(content)
                if user_match:
                    entry["user_id"], entry["action"] = user_match.groups()
                else:
                    api_match = api_pattern.match(content)
                    if api_match:
                        endpoint, latency = api_match.groups()
                        entry["endpoint"] = endpoint
                        entry["latency_ms"] = int(latency) if latency else 0
            
            entries.append(entry)
            
    return entries

def transform_data(entries: List[LogEntry]) -> Dict:
    """
    Processes raw log entries into aggregated metrics.
    
    Args:
        entries: List of parsed LogEntry objects.
        
    Returns:
        A dictionary containing:
        - error_counts: Dict[str, int]
        - api_latencies: Dict[str, List[int]]
        - active_sessions: Set[str]
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions = set()

    for entry in entries:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        elif entry["level"] == "INFO" and entry["user_id"]:
            uid = entry["user_id"]
            action = entry["action"] or ""
            if "logged in" in action:
                sessions.add(uid)
            elif "logged out" in action:
                sessions.discard(uid)
        
        elif entry["level"] == "INFO" and entry["endpoint"]:
            ep = entry["endpoint"]
            api_latencies.setdefault(ep, []).append(entry["latency_ms"] or 0)

    return {
        "error_counts": error_counts,
        "api_latencies": api_latencies,
        "active_sessions": sessions
    }

def load_metrics(config: Config, metrics: Dict) -> None:
    """
    Persists metrics to the SQLite database using parameterized queries.
    
    Args:
        config: Configuration object.
        metrics: Processed metrics from transform_data.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Insert errors
        error_data = [(now, msg, count) for msg, count in metrics["error_counts"].items()]
        cursor.executemany("INSERT INTO errors VALUES (?, ?, ?)", error_data)

        # Insert API metrics
        api_data = []
        for ep, times in metrics["api_latencies"].items():
            avg = sum(times) / len(times) if times else 0
            api_data.append((now, ep, avg))
        cursor.executemany("INSERT INTO api_metrics VALUES (?, ?, ?)", api_data)
        
        conn.commit()

def generate_report(metrics: Dict, output_path: str) -> None:
    """
    Generates an HTML report from the processed metrics.
    
    Args:
        metrics: Processed metrics from transform_data.
        output_path: Path to save the HTML file.
    """
    error_counts = metrics["error_counts"]
    api_latencies = metrics["api_latencies"]
    session_count = len(metrics["active_sessions"])

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
    
    for ep, times in api_latencies.items():
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
    """
    Orchestrates the Extract, Transform, Load and Reporting pipeline.
    """
    config = Config()
    
    # Extract
    entries = extract_logs(config.log_file)
    
    # Transform
    metrics = transform_data(entries)
    
    # Load
    load_metrics(config, metrics)
    
    # Report
    generate_report(metrics, "report.html")
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Setup dummy log if not exists for testing
    config = Config()
    if not os.path.exists(config.log_file):
        with open(config.log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
