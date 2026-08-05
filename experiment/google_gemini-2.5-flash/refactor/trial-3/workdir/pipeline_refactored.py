import datetime
import os
import re
import sqlite3
from typing import List, Dict, Tuple

# --- Configuration from Environment Variables ---
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
# These are kept for completeness, but sqlite3 does not use them directly.
# If a different DB were used, these would be relevant.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# --- Regex Patterns for Log Parsing ---
ERROR_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$")
INFO_USER_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\d+) (?P<action>.*)$")
INFO_API_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")
WARN_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$")

def extract_log_data(log_file_path: str) -> Tuple[List[Dict], Dict[str, str], List[Dict]]:
    """
    Extracts and parses log data from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of dictionaries for general log events (errors, warnings, user actions).
            - A dictionary tracking active user sessions (user_id -> login_timestamp).
            - A list of dictionaries for API call metrics.
    """
    general_events: List[Dict] = []
    active_sessions: Dict[str, str] = {}
    api_call_metrics: List[Dict] = []

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return general_events, active_sessions, api_call_metrics

    with open(log_file_path, "r") as f:
        for line in f:
            if match := ERROR_PATTERN.match(line):
                general_events.append({"d": match["timestamp"], "t": "ERR", "m": match["message"].strip()})
            elif match := INFO_USER_PATTERN.match(line):
                user_id = match["user_id"]
                action = match["action"].strip()
                if "logged in" in action:
                    active_sessions[user_id] = match["timestamp"]
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
                general_events.append({"d": match["timestamp"], "t": "USR", "u": user_id, "a": action})
            elif match := INFO_API_PATTERN.match(line):
                api_call_metrics.append({"d": match["timestamp"], "endpoint": match["endpoint"], "ms": int(match["duration"])})
            elif match := WARN_PATTERN.match(line):
                general_events.append({"d": match["timestamp"], "t": "WARN", "m": match["message"].strip()})
    return general_events, active_sessions, api_call_metrics

def transform_error_data(log_events: List[Dict]) -> Dict[str, int]:
    """
    Aggregates error messages and counts their occurrences.

    Args:
        log_events: A list of general log event dictionaries.

    Returns:
        A dictionary where keys are error messages and values are their counts.
    """
    error_summary: Dict[str, int] = {}
    for event in log_events:
        if event["t"] == "ERR":
            msg = event["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def transform_api_metrics(api_call_metrics: List[Dict]) -> Dict[str, float]:
    """
    Calculates the average latency for each API endpoint.

    Args:
        api_call_metrics: A list of dictionaries for API call metrics.

    Returns:
        A dictionary where keys are API endpoints and values are their average latencies in ms.
    """
    endpoint_durations: Dict[str, List[int]] = {}
    for call in api_call_metrics:
        endpoint_durations.setdefault(call["endpoint"], []).append(call["ms"])

    api_latency_stats: Dict[str, float] = {}
    for ep, durations in endpoint_durations.items():
        api_latency_stats[ep] = sum(durations) / len(durations)
    return api_latency_stats

def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, float],
) -> None:
    """
    Connects to the SQLite database and loads processed error and API latency data.
    Uses parameterized queries to prevent SQL injection.

    Note: DB_HOST, DB_PORT, DB_USER, DB_PASS are defined but not used by sqlite3.
    They would be relevant for other database systems.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Dictionary of error messages and their counts.
        api_latency_stats: Dictionary of API endpoints and their average latencies.
    """
    print(f"Connecting to SQLite database: {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    now = datetime.datetime.now().isoformat()

    # Insert error summary with parameterized query
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))

    # Insert API metrics with parameterized query
    for ep, avg in api_latency_stats.items():
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))

    conn.commit()
    conn.close()
    print("Data loaded to database successfully.")

def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, float],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report summarizing error, API latency, and active session data.

    Args:
        error_summary: Dictionary of error messages and their counts.
        api_latency_stats: Dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")

def main() -> None:
    """
    Main function to orchestrate the log processing and report generation pipeline.
    """
    print(f"Starting data processing at {datetime.datetime.now()}...")

    # Ensure a log file exists for demonstration
    if not os.path.exists(LOG_FILE):
        print(f"Creating dummy log file: {LOG_FILE}")
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /products took 120ms\n")
            f.write("2024-01-01 12:16:00 ERROR Network unreachable\n")


    # Extract
    general_events, active_sessions, api_call_metrics = extract_log_data(LOG_FILE)
    active_sessions_count = len(active_sessions)

    # Transform
    error_summary = transform_error_data(general_events)
    api_latency_stats = transform_api_metrics(api_call_metrics)

    # Load to DB
    load_to_database(DB_PATH, error_summary, api_latency_stats)

    # Generate Report
    generate_report_html(error_summary, api_latency_stats, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
