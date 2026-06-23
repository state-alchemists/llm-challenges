import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

def get_config() -> Dict[str, Any]:
    """
    Retrieves configuration from environment variables with default fallbacks.

    Returns:
        A dictionary containing configuration parameters.
    """
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "5432")),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
    }

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regular expressions.

    Args:
        line: The log line to parse.

    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match a known pattern.
    """
    error_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$")
    user_info_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.*)$")
    api_call_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$")
    warn_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$")

    if (match := error_pattern.match(line)):
        return {"d": match.group(1), "t": "ERR", "m": match.group(2).strip()}
    elif (match := user_info_pattern.match(line)):
        return {"d": match.group(1), "t": "USR", "u": match.group(2), "a": match.group(3).strip()}
    elif (match := api_call_pattern.match(line)):
        return {"d": match.group(1), "t": "API", "endpoint": match.group(2), "ms": int(match.group(3))}
    elif (match := warn_pattern.match(line)):
        return {"d": match.group(1), "t": "WARN", "m": match.group(2).strip()}
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the log file by parsing each line.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
        - A list of all parsed log entries.
        - A dictionary of active user sessions (user ID to login timestamp).
        - A list of API call entries.
    """
    parsed_logs: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    parsed_logs.append(parsed_line)

                    if parsed_line["t"] == "USR":
                        uid = parsed_line["u"]
                        action = parsed_line["a"]
                        if "logged in" in action:
                            sessions[uid] = parsed_line["d"]
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                    elif parsed_line["t"] == "API":
                        api_calls.append(parsed_line)
    return parsed_logs, sessions, api_calls

def transform_error_data(parsed_logs: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Transforms parsed log entries to summarize error counts.

    Args:
        parsed_logs: A list of parsed log dictionaries.

    Returns:
        A dictionary where keys are error messages and values are their counts.
    """
    error_summary: Dict[str, int] = {}
    for entry in parsed_logs:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def transform_api_latency_data(api_calls: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Transforms API call entries to calculate average latencies per endpoint.

    Args:
        api_calls: A list of API call dictionaries.

    Returns:
        A dictionary where keys are API endpoints and values are their average latencies in milliseconds.
    """
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_stats.items()
    }
    return api_latency

def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Initializes the SQLite database connection and creates necessary tables.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        An active SQLite database connection object.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn

def load_error_metrics(conn: sqlite3.Connection, error_summary: Dict[str, int]) -> None:
    """
    Loads error summary data into the database using parameterized queries.

    Args:
        conn: The SQLite database connection.
        error_summary: A dictionary of error messages and their counts.
    """
    c = conn.cursor()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )
    conn.commit()

def load_api_metrics(conn: sqlite3.Connection, api_latency: Dict[str, float]) -> None:
    """
    Loads API latency metrics into the database using parameterized queries.

    Args:
        conn: The SQLite database connection.
        api_latency: A dictionary of API endpoints and their average latencies.
    """
    c = conn.cursor()
    for ep, avg in api_latency.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )
    conn.commit()

def generate_html_report(
    error_summary: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions_count: int,
    output_file: str,
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: Dictionary of error messages and their counts.
        api_latency: Dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The path where the HTML report will be saved.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

def main():
    """
    Main function to orchestrate the log processing and report generation.
    """
    config = get_config()
    log_file_path = config["LOG_FILE"]
    db_path = config["DB_PATH"]
    # db_host = config["DB_HOST"]
    # db_port = config["DB_PORT"]
    # db_user = config["DB_USER"]
    # db_pass = config["DB_PASS"]

    print(f"Connecting to {config['DB_HOST']}:{config['DB_PORT']} as {config['DB_USER']}...")

    parsed_logs, sessions, api_calls = extract_log_data(log_file_path)
    error_summary = transform_error_data(parsed_logs)
    api_latency = transform_api_latency_data(api_calls)

    conn = initialize_database(db_path)
    try:
        load_error_metrics(conn, error_summary)
        load_api_metrics(conn, api_latency)
    finally:
        conn.close()

    generate_html_report(error_summary, api_latency, len(sessions), "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = get_config()
    log_file_path = config["LOG_FILE"]
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
