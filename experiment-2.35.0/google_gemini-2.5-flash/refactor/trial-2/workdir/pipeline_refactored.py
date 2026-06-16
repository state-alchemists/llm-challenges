import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

def load_config() -> Dict[str, Any]:
    """Loads configuration from environment variables."""
    config = {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "5432")),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html"),
    }
    return config

def parse_log_file(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Parses the server log file and extracts error, user session, and API call information.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing three lists:
        - A list of parsed log entries (errors, warnings, user actions).
        - A dictionary of active user sessions (user_id: login_timestamp).
        - A list of API call details (timestamp, endpoint, duration_ms).
    """
    parsed_entries: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    log_pattern = re.compile(r"""^(\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}}:\\d{{2}}) (INFO|ERROR|WARN) (.*)""")
    user_login_pattern = re.compile(r"""User (\\w+) logged in""")
    user_logout_pattern = re.compile(r"""User (\\w+) logged out""")
    api_call_pattern = re.compile(r"""API (/\\S+) took (\\d+)ms""")

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_entries, sessions, api_calls

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if not match:
                continue

            timestamp_str, level, message = match.groups()

            if level == "ERROR":
                parsed_entries.append({"d": timestamp_str, "t": "ERR", "m": message.strip()})
            elif level == "WARN":
                parsed_entries.append({"d": timestamp_str, "t": "WARN", "m": message.strip()})
            elif level == "INFO":
                user_login_match = user_login_pattern.search(message)
                user_logout_match = user_logout_pattern.search(message)
                api_call_match = api_call_pattern.search(message)

                if user_login_match:
                    uid = user_login_match.group(1)
                    sessions[uid] = timestamp_str
                    parsed_entries.append({"d": timestamp_str, "t": "USR", "u": uid, "a": "logged in"})
                elif user_logout_match:
                    uid = user_logout_match.group(1)
                    if uid in sessions:
                        sessions.pop(uid)
                    parsed_entries.append({"d": timestamp_str, "t": "USR", "u": uid, "a": "logged out"})
                elif api_call_match:
                    endpoint, duration = api_call_match.groups()
                    api_calls.append({"d": timestamp_str, "endpoint": endpoint, "ms": int(duration)})
    return parsed_entries, sessions, api_calls


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    return conn

def initialize_db(conn: sqlite3.Connection) -> None:
    """Creates necessary tables in the database if they don't exist."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()

def collect_error_summary(parsed_entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregates error messages and their counts from parsed log entries."""
    error_summary: Dict[str, int] = {}
    for entry in parsed_entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def insert_error_summary(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """Inserts error summary data into the 'errors' table using parameterized queries."""
    c = conn.cursor()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )
    conn.commit()

def collect_api_latency_summary(api_calls: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Aggregates API call latencies by endpoint."""
    api_latency_summary: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        api_latency_summary.setdefault(ep, []).append(call["ms"])
    return api_latency_summary

def insert_api_metrics(conn: sqlite3.Connection, api_latency_summary: Dict[str, List[int]]) -> None:
    """Inserts API latency metrics into the 'api_metrics' table using parameterized queries."""
    c = conn.cursor()
    for ep, times in api_latency_summary.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )
    conn.commit()


def main():
    config = load_config()
    print(f"Connecting to {config['DB_HOST']}:{config['DB_PORT']} as {config['DB_USER']}...")
    
    conn = get_db_connection(config["DB_PATH"])
    initialize_db(conn)

    parsed_entries, sessions, api_calls = parse_log_file(config["LOG_FILE"])
    print(f"Parsed {len(parsed_entries)} log entries, {len(sessions)} active sessions, {len(api_calls)} API calls.")

    # Process and insert errors
    error_summary = collect_error_summary(parsed_entries)
    insert_error_summary(conn, error_summary)

    # Process and insert API metrics
    api_latency_summary = collect_api_latency_summary(api_calls)
    insert_api_metrics(conn, api_latency_summary)

    report_file_path = config["REPORT_FILE"]
    generate_report_html(report_file_path, error_summary, api_latency_summary, len(sessions))

    print(f"Report generated at {report_file_path}")
    print(f"Job finished at {datetime.datetime.now()}")


def generate_report_html(report_file_path: str, error_summary: Dict[str, int], 
                           api_latency_summary: Dict[str, List[int]], active_sessions_count: int) -> None:
    """Generates an HTML report from the processed data."""
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency_summary.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"    

    with open(report_file_path, "w") as f:
        f.write(out)


