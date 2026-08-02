import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# --- Configuration ---
# Load from environment variables with defaults from original script for compatibility
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
class PipelineStats:
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latencies: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: set = field(default_factory=set)

def extract_logs(file_path: str) -> List[LogEntry]:
    """
    Parses the server log file using regex to extract structured log entries.
    
    Args:
        file_path: Path to the log file.
        
    Returns:
        A list of LogEntry objects.
    """
    entries = []
    # Regex patterns for different log levels
    # Format: YYYY-MM-DD HH:MM:SS LEVEL Message
    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s(\w+)\s(.*)$")
    user_pattern = re.compile(r"User (\w+) (.*)$")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(file_path):
        return entries

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = base_pattern.match(line)
            if not match:
                continue
                
            dt, lvl, msg = match.groups()
            entry = LogEntry(timestamp=dt, level=lvl, message=msg)

            if lvl == "ERROR" or lvl == "WARN":
                # Message is already captured by base_pattern
                pass
            elif lvl == "INFO":
                if "User" in msg:
                    u_match = user_pattern.match(msg)
                    if u_match:
                        entry.user_id, entry.action = u_match.groups()
                elif "API" in msg:
                    a_match = api_pattern.search(msg)
                    if a_match:
                        entry.endpoint, lat = a_match.groups()
                        entry.latency_ms = int(lat)
            
            entries.append(entry)
    return entries

def transform_logs(entries: List[LogEntry]) -> Tuple[PipelineStats, List[Tuple[str, int]]]:
    """
    Processes log entries into aggregated stats for reporting and DB loading.
    
    Args:
        entries: List of parsed log entries.
        
    Returns:
        A tuple containing a PipelineStats object and a list of (error_msg, count) tuples.
    """
    stats = PipelineStats()
    
    for entry in entries:
        if entry.level == "ERROR":
            stats.error_counts[entry.message] = stats.error_counts.get(entry.message, 0) + 1
        
        elif entry.level == "INFO" and entry.user_id:
            if "logged in" in (entry.action or ""):
                stats.active_sessions.add(entry.user_id)
            elif "logged out" in (entry.action or ""):
                stats.active_sessions.discard(entry.user_id)
        
        elif entry.level == "INFO" and entry.endpoint:
            if entry.latency_ms is not None:
                stats.api_latencies.setdefault(entry.endpoint, []).append(entry.latency_ms)

    return stats, list(stats.error_counts.items())

def load_to_db(error_items: List[Tuple[str, int]], api_stats: Dict[str, List[int]]) -> None:
    """
    Loads aggregated metrics into the SQLite database using parameterized queries.
    
    Args:
        error_items: List of (message, count) tuples.
        api_stats: Dict mapping endpoints to lists of latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Parameterized inserts to prevent SQL injection
        for msg, count in error_items:
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for ep, times in api_stats.items():
            avg = sum(times) / len(times) if times else 0
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg))
        
        conn.commit()

def generate_report(stats: PipelineStats) -> None:
    """
    Generates an HTML report based on the processed statistics.
    
    Args:
        stats: The aggregated pipeline statistics.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    
    # Error Summary
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in stats.error_counts.items():
        out += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    # API Latency
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in stats.api_latencies.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    # Active Sessions
    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(stats.active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def run_pipeline() -> None:
    """
    Executes the full Extract -> Transform -> Load pipeline.
    """
    # Extract
    entries = extract_logs(LOG_FILE)
    
    # Transform
    stats, error_summaries = transform_logs(entries)
    
    # Load
    load_to_db(error_summaries, stats.api_latencies)
    generate_report(stats)
    
    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Mock data generation for testing (kept from original script)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    run_pipeline()
