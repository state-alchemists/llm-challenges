import datetime
import os
import sqlite3
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class Config:
    """Configuration for the log processing pipeline."""
    DB_PATH: str
    LOG_FILE: str
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str

def load_config() -> Config:
    """Loads configuration from environment variables."""
    return Config(
        DB_PATH=os.environ.get("DB_PATH", "metrics.db"),
        LOG_FILE=os.environ.get("LOG_FILE", "server.log"),
        DB_HOST=os.environ.get("DB_HOST", "localhost"),
        DB_PORT=int(os.environ.get("DB_PORT", "5432")),
        DB_USER=os.environ.get("DB_USER", "admin"),
        DB_PASS=os.environ.get("DB_PASS", "password123"),
    )

@dataclass
class LogEntry:
    """Represents a parsed log entry."""
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None

# Regex patterns for different log entry types
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$")
USER_LOG_PATTERN = re.compile(r"User (\w+) (.*)$")
API_LOG_PATTERN = re.compile(r"API (/\S+) took (\d+)ms$")

def parse_log_entry(line: str) -> Optional[LogEntry]:
    """Parses a single log line using regex and returns a LogEntry object."""
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    timestamp_str, level, message = match.groups()
    
    if level == "ERROR" or level == "WARN":
        return LogEntry(timestamp=timestamp_str, level=level, message=message.strip())
    elif level == "INFO":
        user_match = USER_LOG_PATTERN.search(message)
        if user_match:
            user_id, action = user_match.groups()
            return LogEntry(timestamp=timestamp_str, level=level, message=message.strip(), user_id=user_id, action=action.strip())
        
        api_match = API_LOG_PATTERN.search(message)
        if api_match:
            endpoint, duration_ms_str = api_match.groups()
            return LogEntry(timestamp=timestamp_str, level=level, message=message.strip(), endpoint=endpoint, duration_ms=int(duration_ms_str))
    return LogEntry(timestamp=timestamp_str, level=level, message=message.strip())

def extract_log_data(config: Config) -> List[LogEntry]:
    """Extracts log data from the log file using regex parsing."""
    log_entries: List[LogEntry] = []
    if os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, "r") as f:
            for line in f:
                entry = parse_log_entry(line)
                if entry:
                    log_entries.append(entry)
    return log_entries

def transform_log_entries(log_entries: List[LogEntry]) -> Dict[str, Any]:
    """Transforms raw log entries into structured data for reporting and database loading."""
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in log_entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.level == "INFO" and entry.user_id and entry.action:
            if "logged in" in entry.action:
                active_sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in active_sessions:
                active_sessions.pop(entry.user_id)
        elif entry.level == "INFO" and entry.endpoint and entry.duration_ms is not None:
            api_latencies.setdefault(entry.endpoint, []).append(entry.duration_ms)

    return {
        "error_counts": error_counts,
        "api_latencies": api_latencies,
        "active_sessions_count": len(active_sessions),
    }

def load_to_database(config: Config, transformed_data: Dict[str, Any]) -> None:
    """Loads transformed data into the SQLite database."""
    print(f"Connecting to {config.DB_HOST}:{config.DB_PORT} as {config.DB_USER}...")

    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in transformed_data["error_counts"].items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

    for ep, times in transformed_data["api_latencies"].items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )

    conn.commit()
    conn.close()
    print("Data loaded to database.")

def generate_report(transformed_data: Dict[str, Any]) -> None:
    """Generates the HTML report from the transformed data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in transformed_data["error_counts"].items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in transformed_data["api_latencies"].items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{transformed_data['active_sessions_count']} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

    print("Report generated: report.html")

def main():
    """Main function to run the log processing pipeline."""
    config = load_config()
    # Create dummy log file if it doesn't exist for demonstration
    if not os.path.exists(config.LOG_FILE):
        with open(config.LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    log_entries = extract_log_data(config)
    transformed_data = transform_log_entries(log_entries)
    load_to_database(config, transformed_data)
    generate_report(transformed_data)
    print("Job finished at " + str(datetime.datetime.now()))

if __name__ == "__main__":
    main()
