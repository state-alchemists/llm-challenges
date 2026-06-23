import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE_PATH", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")


def extract_logs(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the server log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing three lists:
        - d_list: A list of dictionaries for errors and warnings.
        - sessions: A dictionary mapping user IDs to login timestamps.
        - api_calls: A list of dictionaries for API call metrics.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        print(f"Log file not found at {log_file_path}")
        return d_list, sessions, api_calls

    log_pattern = re.compile(r"^(\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) (INFO|WARN|ERROR) (.*)$")
    user_login_pattern = re.compile(r"User (\w+) logged in")
    user_logout_pattern = re.compile(r"User (\w+) logged out")
    api_call_pattern = re.compile(r"API (/[\w/]+) took (\d+)ms")

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if not match:
                continue

            dt, lvl, message = match.groups()

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": message.strip()})
            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": message.strip()})
            elif lvl == "INFO":
                if "User" in message:
                    login_match = user_login_pattern.search(message)
                    logout_match = user_logout_pattern.search(message)
                    if login_match:
                        uid = login_match.group(1)
                        sessions[uid] = dt
                        d_list.append({"d": dt, "t": "USR", "u": uid, "a": f"User {uid} logged in"})
                    elif logout_match:
                        uid = logout_match.group(1)
                        if uid in sessions:
                            sessions.pop(uid)
                        d_list.append({"d": dt, "t": "USR", "u": uid, "a": f"User {uid} logged out"})
                elif "API" in message:
                    api_match = api_call_pattern.search(message)
                    if api_match:
                        endpoint, dur = api_match.groups()
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": int(dur)})
                    else:
                        print(f"Warning: Could not parse API call in line: {line.strip()}")
            else:
                print(f"Warning: Unhandled log level '{lvl}' in line: {line.strip()}")
    return d_list, sessions, api_calls


def transform_data(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms extracted log data into summarized metrics.

    Args:
        d_list: List of dictionaries for errors and warnings.
        api_calls: List of dictionaries for API call metrics.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - endpoint_stats: A dictionary mapping API endpoints to a list of their latencies.
    """
    error_summary: Dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    return error_summary, endpoint_stats


def load_data(
    db_path: str,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """
    Loads transformed data into the SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary mapping error messages to their counts.
        endpoint_stats: A dictionary mapping API endpoints to a list of their latencies.
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

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()
    print("Data loaded into database.")


def generate_report(
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary mapping error messages to their counts.
        endpoint_stats: A dictionary mapping API endpoints to a list of their latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\\n<head><title>System Report</title></head>\\n<body>\\n"
    out += "<h1>Error Summary</h1>\\n<ul>\\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += "<h2>API Latency</h2>\\n<table border=\'1\'>\\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += "<h2>Active Sessions</h2>\\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\\n"
    out += "</body>\\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")


def main():
    """
    Main function to run the log processing pipeline.
    """
    d_list, sessions, api_calls = extract_logs(LOG_FILE)
    error_summary, endpoint_stats = transform_data(d_list, api_calls)
    load_data(DB_PATH, error_summary, endpoint_stats)
    generate_report(error_summary, endpoint_stats, len(sessions))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\\n")
    main()