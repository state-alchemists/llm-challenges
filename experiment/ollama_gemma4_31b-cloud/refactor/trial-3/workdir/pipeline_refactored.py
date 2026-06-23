import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TypedDict

# --- Types ---
class LogEntry(TypedDict):
    timestamp: str
    level: str
    message: str
    user_id: Optional[str]
    action: Optional[str]
    endpoint: Optional[str]
    latency: Optional[int]

@dataclass
class Config:
    """Configuration loaded from environment variables."""
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "metrics.db"))
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "server.log"))
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "admin"))
    db_pass: str = field(default_factory=lambda: os.getenv("DB_PASS", "password123"))

# --- Extract ---
def parse_logs(log_path: str) -> Tuple[List[LogEntry], Dict[str, str]]:
    """
    Parses the server log file using regex.
    Returns a list of parsed entries and a map of active sessions (user_id -> login_time).
    """
    entries: List[LogEntry] = []
    sessions: Dict[str, str] = {}

    # Patterns
    # General: YYYY-MM-DD HH:MM:SS LEVEL ...
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.+)$")
    # User activity: User <id> <action>
    user_pattern = re.compile(r"User (\S+) (.+)")
    # API call: API <endpoint> took <ms>ms
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(log_path):
        return entries, sessions

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            match = base_pattern.match(line)
            if not match:
                continue

            timestamp, level, content = match.groups()
            entry: LogEntry = {"timestamp": timestamp, "level": level, "message": content, 
                              "user_id": None, "action": None, "endpoint": None, "latency": None}

            if level == "ERROR":
                entry["message"] = content
            elif level == "WARN":
                entry["message"] = content
            elif level == "INFO":
                # Check for User activity
                user_match = user_pattern.search(content)
                if user_match:
                    uid, action = user_match.groups()
                    entry["user_id"] = uid
                    entry["action"] = action
                    if "logged in" in action:
                        sessions[uid] = timestamp
                    elif "logged out" in action:
                        sessions.pop(uid, None)
                else:
                    # Check for API activity
                    api_match = api_pattern.search(content)
                    if api_match:
                        endpoint, latency = api_match.groups()
                        entry["endpoint"] = endpoint
                        entry["latency"] = int(latency)
            
            entries.append(entry)
            
    return entries, sessions

# --- Transform ---
def aggregate_metrics(entries: List[LogEntry]) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Aggregates error counts and API latencies from log entries.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}

    for entry in entries:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif entry["endpoint"] and entry["latency"] is not None:
            ep = entry["endpoint"]
            api_latencies.setdefault(ep, []).append(entry["latency"])

    return error_counts, api_latencies

# --- Load ---
def save_to_db(config: Config, error_counts: Dict[str, int], api_latencies: Dict[str, List[int]]) -> None:
    """
    Persists aggregated metrics to SQLite using parameterized queries.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    
    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        now = datetime.datetime.now().isoformat()

        for msg, count in error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_latencies.items():
            avg = sum(times) / len(times)
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

# --- Report ---
def generate_report(output_path: str, error_counts: Dict[str, int], api_latencies: Dict[str, List[int]], session_count: int) -> None:
    """
    Generates the HTML report with the provided metrics.
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

# --- Main ---
def main():
    config = Config()
    
    # Extract
    entries, sessions = parse_logs(config.log_file)
    
    # Transform
    error_counts, api_latencies = aggregate_metrics(entries)
    
    # Load
    save_to_db(config, error_counts, api_latencies)
    
    # Report
    generate_report("report.html", error_counts, api_latencies, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Ensure dummy log file for testing if not present (keeping original script's behavior)
    if not os.path.exists("server.log"):
        with open("server.log", "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    main()
