import datetime
import os
import sqlite3

# Hardcoded config — change these manually for each environment
import re
import os
from typing import Dict, List, Any, Tuple

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts log data from the specified log file, parsing errors, user sessions, and API calls.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
        - A list of parsed log entries (errors, warnings, user actions).
        - A dictionary of active user sessions.
        - A list of API call metrics.
    """
    parsed_logs: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    # Regex patterns for different log lines
    error_pattern = re.compile(r"^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) ERROR (?P<message>.*)")
    info_user_pattern = re.compile(r"^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) INFO User (?P<user_id>\w+) (?P<action>.*)")
    info_api_pattern = re.compile(r"^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) INFO API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")
    warn_pattern = re.compile(r"^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) WARN (?P<message>.*)")

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                if error_match := error_pattern.match(line):
                    parsed_logs.append({
                        "d": error_match.group("timestamp"),
                        "t": "ERR",
                        "m": error_match.group("message").strip()
                    })
                elif info_user_match := info_user_pattern.match(line):
                    user_id = info_user_match.group("user_id")
                    action = info_user_match.group("action").strip()
                    if "logged in" in action:
                        sessions[user_id] = info_user_match.group("timestamp")
                    elif "logged out" in action and user_id in sessions:
                        sessions.pop(user_id)
                    parsed_logs.append({
                        "d": info_user_match.group("timestamp"),
                        "t": "USR",
                        "u": user_id,
                        "a": action
                    })
                elif info_api_match := info_api_pattern.match(line):
                    api_calls.append({
                        "d": info_api_match.group("timestamp"),
                        "endpoint": info_api_match.group("endpoint"),
                        "ms": int(info_api_match.group("duration"))
                    })
                elif warn_match := warn_pattern.match(line):
                    parsed_logs.append({
                        "d": warn_match.group("timestamp"),
                        "t": "WARN",
                        "m": warn_match.group("message").strip()
                    })
    return parsed_logs, sessions, api_calls


def transform_data(
    parsed_logs: List[Dict[str, str]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Transforms extracted log data into summarized error counts and API latency statistics.

    Args:
        parsed_logs: A list of parsed log entries.
        api_calls: A list of API call metrics.

    Returns:
        A tuple containing:
        - A dictionary with error messages as keys and their counts as values.
        - A dictionary with API endpoints as keys and their average latency (ms) as values.
    """
    error_summary: Dict[str, int] = {}
    for entry in parsed_logs:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    api_latency: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        api_latency.setdefault(ep, []).append(call["ms"])

    api_avg_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_latency.items()
    }
    return error_summary, api_avg_latency


def load_data_to_db(
    db_path: str, error_summary: Dict[str, int], api_avg_latency: Dict[str, float]
) -> None:
    """
    Loads transformed data into the SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: Dictionary of error messages and their counts.
        api_avg_latency: Dictionary of API endpoints and their average latencies.
    """
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, avg in api_avg_latency.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: Dict[str, int],
    api_avg_latency: Dict[str, float],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: Dictionary of error messages and their counts.
        api_avg_latency: Dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += "<h2>API Latency</h2>\\n<table border='1'>\\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\\n"
    for ep, avg in api_avg_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += "<h2>Active Sessions</h2>\\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\\n"
    out += "</body>\\n</html>"

    with open(output_file, "w") as f:
        f.write(out)


def main():
    \"\"\"
    Main function to orchestrate the log processing and report generation.
    \"\"\"
    # 1. Extract
    parsed_logs, sessions, api_calls = extract_log_data(LOG_FILE)

    # 2. Transform
    error_summary, api_avg_latency = transform_data(parsed_logs, api_calls)

    # 3. Load to DB
    load_data_to_db(DB_PATH, error_summary, api_avg_latency)

    # 4. Generate Report
    generate_report(error_summary, api_avg_latency, len(sessions))

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
