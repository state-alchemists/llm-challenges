import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Tuple

def get_config() -> Dict[str, str]:
    """
    Retrieves configuration from environment variables.

    Returns:
        A dictionary containing configuration values.
    """
    config = {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
    }
    return config

def extract_logs(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing lists of raw data, sessions, and API calls.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    log_pattern = re.compile(
        r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"(?P<level>\w+) "
        r"(?P<message>.*)$"
    )
    user_login_pattern = re.compile(r"User (\d+) logged in")
    user_logout_pattern = re.compile(r"User (\d+) logged out")
    api_call_pattern = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                match = log_pattern.match(line)
                if not match:
                    continue

                dt = match.group("datetime")
                level = match.group("level")
                message = match.group("message")

                if level == "ERROR":
                    d_list.append({"d": dt, "t": "ERR", "m": message.strip()})
                elif level == "INFO":
                    if "User" in message:
                        user_login_match = user_login_pattern.search(message)
                        user_logout_match = user_logout_pattern.search(message)
                        if user_login_match:
                            uid = user_login_match.group(1)
                            sessions[uid] = dt
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": "logged in"})
                        elif user_logout_match:
                            uid = user_logout_match.group(1)
                            if uid in sessions:
                                sessions.pop(uid)
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": "logged out"})
                    elif "API" in message:
                        api_match = api_call_pattern.search(message)
                        if api_match:
                            endpoint = api_match.group("endpoint")
                            dur = int(api_match.group("duration"))
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                elif level == "WARN":
                    d_list.append({"d": dt, "t": "WARN", "m": message.strip()})
    return d_list, sessions, api_calls

def transform_data(d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms extracted log data into summarized error counts and API endpoint statistics.

    Args:
        d_list: A list of parsed log entries.
        api_calls: A list of parsed API call entries.

    Returns:
        A tuple containing error message counts and a dictionary of API endpoint latencies.
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

def load_data_to_db(db_path: str, error_summary: Dict[str, int], endpoint_stats: Dict[str, List[int]]) -> None:
    """
    Loads transformed data into an SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error message counts.
        endpoint_stats: A dictionary of API endpoint latencies.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )
    conn.commit()
    conn.close()

def generate_report(error_summary: Dict[str, int], endpoint_stats: Dict[str, List[int]], active_sessions_count: int) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error message counts.
        endpoint_stats: A dictionary of API endpoint latencies.
        active_sessions_count: The number of currently active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def main():
    """
    Main function to run the log processing pipeline.
    """
    config = get_config()
    db_path = config["DB_PATH"]
    log_file = config["LOG_FILE"]
    db_host = config["DB_HOST"]
    db_port = config["DB_PORT"]
    db_user = config["DB_USER"]

    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    raw_data, sessions, api_calls = extract_logs(log_file)
    error_summary, endpoint_stats = transform_data(raw_data, api_calls)
    load_data_to_db(db_path, error_summary, endpoint_stats)
    generate_report(error_summary, endpoint_stats, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = get_config()
    log_file = config["LOG_FILE"]
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
