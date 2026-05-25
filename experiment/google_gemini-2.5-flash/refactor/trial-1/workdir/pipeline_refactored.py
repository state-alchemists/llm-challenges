import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Tuple

# Configuration loaded from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex for parsing log lines
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>(INFO|ERROR|WARN)) "
    r"(?P<message>.*)$"
)

USER_LOGIN_PATTERN = re.compile(r"User (?P<user_id>\d+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (?P<user_id>\d+) logged out")
API_CALL_PATTERN = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")


def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from log file, parsing error messages, user sessions, and API calls.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of parsed log entries (errors, warnings, user actions).
            - A dictionary of active user sessions.
            - A list of API call metrics.
    """
    parsed_entries: List[Dict[str, Any]] = []
    active_sessions: Dict[str, str] = {}
    api_call_metrics: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_entries, active_sessions, api_call_metrics

    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            message = match.group("message").strip()

            if level == "ERROR":
                parsed_entries.append({"dt": timestamp, "type": "ERR", "message": message})
            elif level == "WARN":
                parsed_entries.append({"dt": timestamp, "type": "WARN", "message": message})
            elif level == "INFO":
                user_login_match = USER_LOGIN_PATTERN.search(message)
                user_logout_match = USER_LOGOUT_PATTERN.search(message)
                api_call_match = API_CALL_PATTERN.search(message)

                if user_login_match:
                    user_id = user_login_match.group("user_id")
                    active_sessions[user_id] = timestamp
                    parsed_entries.append({"dt": timestamp, "type": "USR", "user_id": user_id, "action": "logged in"})
                elif user_logout_match:
                    user_id = user_logout_match.group("user_id")
                    if user_id in active_sessions:
                        active_sessions.pop(user_id)
                    parsed_entries.append({"dt": timestamp, "type": "USR", "user_id": user_id, "action": "logged out"})
                elif api_call_match:
                    endpoint = api_call_match.group("endpoint")
                    duration = int(api_call_match.group("duration"))
                    api_call_metrics.append({"dt": timestamp, "endpoint": endpoint, "ms": duration})
    
    return parsed_entries, active_sessions, api_call_metrics


def transform_data(
    parsed_entries: List[Dict[str, Any]],
    api_call_metrics: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Transforms the extracted log data into summarized error counts and API latency statistics.

    Args:
        parsed_entries: A list of parsed log entries.
        api_call_metrics: A list of API call metrics.

    Returns:
        A tuple containing:
            - A dictionary where keys are error messages and values are their counts.
            - A dictionary where keys are API endpoints and values are their average latencies in ms.
    """
    error_summary: Dict[str, int] = {}
    for entry in parsed_entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_call_metrics:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_latency: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        api_latency[ep] = sum(times) / len(times)

    return error_summary, api_latency


def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency: Dict[str, float]
) -> None:
    """
    Loads the transformed data into an SQLite database, using parameterized queries.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their average latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert error summary
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    # Insert API latency metrics
    for ep, avg in api_latency.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their average latencies.
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
    for ep, avg in api_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)


def main():
    """Main function to orchestrate the log processing and report generation."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed_entries, active_sessions, api_call_metrics = extract_log_data(LOG_FILE)
    error_summary, api_latency = transform_data(parsed_entries, api_call_metrics)
    load_data_to_db(DB_PATH, error_summary, api_latency)
    generate_report(error_summary, api_latency, len(active_sessions))

    print("Job finished at " + str(datetime.datetime.now()))


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