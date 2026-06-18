import re
from typing import Dict, List, Any, Tuple
import os
import datetime
import sqlite3

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
def parse_log_line(line: str) -> Dict[str, Any] | None:
    """Parses a single log line using regex and extracts relevant information.

    Args:
        line: The log line to parse.

    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match a known pattern.
    """
    # Timestamp, Level, Message
    error_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR) (.*)$")
    warn_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (WARN) (.*)$")
    user_info_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO) User (\d+) (.*)$")
    api_info_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO) API (\S+) took (\d+)ms$")

    if match := error_pattern.match(line):
        return {"timestamp": match.group(1), "level": match.group(2), "message": match.group(3).strip()}
    elif match := user_info_pattern.match(line):
        return {"timestamp": match.group(1), "level": match.group(2), "user_id": match.group(3), "action": match.group(4).strip()}
    elif match := api_info_pattern.match(line):
        return {"timestamp": match.group(1), "level": match.group(2), "endpoint": match.group(3), "duration_ms": int(match.group(4))}
    elif match := warn_pattern.match(line):
        return {"timestamp": match.group(1), "level": match.group(2), "message": match.group(3).strip()}
    return None

def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """Extracts and parses log data from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed log entry.
    """
    parsed_logs: List[Dict[str, Any]] = []
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            if parsed_line := parse_log_line(line):
                parsed_logs.append(parsed_line)
    return parsed_logs

def transform_log_data(parsed_logs: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Transforms parsed log data into summarized metrics.

    Args:
        parsed_logs: A list of dictionaries, each representing a parsed log entry.

    Returns:
        A tuple containing:
        - error_counts: A dictionary of error messages and their counts.
        - api_latency: A dictionary mapping API endpoints to a list of their latencies.
        - active_sessions: A dictionary of currently active user sessions (user_id to timestamp).
    """
    error_counts: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in parsed_logs:
        level = entry.get("level")
        timestamp = entry.get("timestamp")

        if level == "ERROR":
            message = entry.get("message")
            if message:
                error_counts[message] = error_counts.get(message, 0) + 1
        elif level == "INFO":
            if "user_id" in entry and "action" in entry:
                user_id = entry["user_id"]
                action = entry["action"]
                if "logged in" in action:
                    active_sessions[user_id] = timestamp
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
            elif "endpoint" in entry and "duration_ms" in entry:
                endpoint = entry["endpoint"]
                duration = entry["duration_ms"]
                api_latency.setdefault(endpoint, []).append(duration)

    return error_counts, api_latency, active_sessions

def load_metrics_to_db(error_counts: Dict[str, int], api_latency: Dict[str, List[int]]) -> None:
    """Connects to the database and loads the processed metrics.

    Args:
        error_counts: A dictionary of error messages and their counts.
        api_latency: A dictionary mapping API endpoints to a list of their latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                  (datetime.datetime.now().isoformat(), msg, count))

    for ep, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                  (datetime.datetime.now().isoformat(), ep, avg))

    conn.commit()
    conn.close()
    print("Metrics loaded to database.")

def generate_report(error_counts: Dict[str, int], api_latency: Dict[str, List[int]], active_sessions: Dict[str, str]) -> None:
    """Generates an HTML report from the processed metrics.

    Args:
        error_counts: A dictionary of error messages and their counts.
        api_latency: A dictionary mapping API endpoints to a list of their latencies.
        active_sessions: A dictionary of currently active user sessions (user_id to timestamp).
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)
    print("Report generated: report.html")

def main():
    """Main function to run the log processing pipeline."""
    print(f"Starting log processing at {datetime.datetime.now()}")
    parsed_logs = extract_log_data(LOG_FILE)
    error_counts, api_latency, active_sessions = transform_log_data(parsed_logs)
    load_metrics_to_db(error_counts, api_latency)
    generate_report(error_counts, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
