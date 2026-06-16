"""
Pipeline Log Processor and Report Generator.

Extracts log events from a server log file, transforms them into aggregated
metrics, and loads them into a database and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration retrieved via environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular expressions for log parsing
LOG_PATTERN: re.Pattern = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>[A-Z]+)\s+(?P<message>.*)$"
)
USER_PATTERN: re.Pattern = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")
API_PATTERN: re.Pattern = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?")


def _process_user_info(
    message: str,
    dt: str,
    sessions: Dict[str, str],
    d_list: List[Dict[str, Any]]
) -> None:
    """
    Parses user action information from an INFO level log message.

    Updates the active user sessions map and logs the user action event.

    Args:
        message: The message body of the log.
        dt: The timestamp of the log event.
        sessions: Active user sessions dictionary to update.
        d_list: Log events list to append user action details.
    """
    user_match = USER_PATTERN.match(message)
    if not user_match:
        return

    uid = user_match.group("uid")
    action = user_match.group("action").strip()

    if "logged in" in action:
        sessions[uid] = dt
    elif "logged out" in action and uid in sessions:
        sessions.pop(uid)

    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})


def _process_api_info(
    message: str,
    dt: str,
    api_calls: List[Dict[str, Any]]
) -> None:
    """
    Parses API execution information from an INFO level log message.

    Logs API latency metrics.

    Args:
        message: The message body of the log.
        dt: The timestamp of the log event.
        api_calls: API metrics list to append API call details.
    """
    api_match = API_PATTERN.match(message)
    if not api_match:
        return

    endpoint = api_match.group("endpoint")
    ms_str = api_match.group("ms")
    ms = int(ms_str) if ms_str else 0

    api_calls.append({"d": dt, "endpoint": endpoint, "ms": ms})


def extract_log_data(
    log_file_path: str
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts structured data from the server log file.

    Parses log lines using regular expressions to extract events, active
    user sessions, and API call latency data.

    Args:
        log_file_path: Path to the log file to parse.

    Returns:
        A tuple containing a list of log events, a sessions map, and a list of API calls.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return d_list, sessions, api_calls

    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except IOError:
        return d_list, sessions, api_calls

    for line in lines:
        match = LOG_PATTERN.match(line.strip())
        if not match:
            continue

        dt = match.group("dt")
        lvl = match.group("level")
        message = match.group("message")

        if lvl == "ERROR":
            d_list.append({"d": dt, "t": "ERR", "m": message.strip()})
        elif lvl == "WARN":
            d_list.append({"d": dt, "t": "WARN", "m": message.strip()})
        elif lvl == "INFO":
            _process_user_info(message, dt, sessions, d_list)
            _process_api_info(message, dt, api_calls)

    return d_list, sessions, api_calls


def transform_metrics(
    d_list: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Transforms extracted logs into aggregated metrics.

    Aggregates the error occurrences and calculates the average latency
    per API endpoint.

    Args:
        d_list: List of parsed log events.
        api_calls: List of parsed API calls.

    Returns:
        A tuple containing a dictionary of error summaries and a dictionary of
        average latency per API endpoint.
    """
    error_summary: Dict[str, int] = {}
    for x in d_list:
        if x.get("t") == "ERR":
            msg = x.get("m", "")
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        if times:
            api_averages[ep] = sum(times) / len(times)
        else:
            api_averages[ep] = 0.0

    return error_summary, api_averages


def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    api_averages: Dict[str, float]
) -> None:
    """
    Loads the transformed metrics into the SQLite database.

    Creates tables if they do not exist, and inserts parameterized rows
    representing error counts and API averages with current timestamp.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Transformed error count metrics.
        api_averages: Transformed API average latency metrics.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count)
            )

        for ep, avg in api_averages.items():
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now_str, ep, avg)
            )

        conn.commit()
    finally:
        conn.close()


def load_report(
    report_path: str,
    error_summary: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions_count: int
) -> None:
    """
    Generates the system HTML report file with the provided metrics.

    Args:
        report_path: Path where the HTML report should be saved.
        error_summary: Error counts dictionary.
        api_averages: API average latency dictionary.
        active_sessions_count: Count of currently active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def _generate_default_log(log_file_path: str) -> None:
    """
    Generates a default server log file with sample entries if it does not exist.

    Args:
        log_file_path: Path where the default log file should be written.
    """
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


def run_pipeline() -> None:
    """
    Runs the complete log processing, database loading, and report generation pipeline.
    """
    # Create default log file if not existing, matching original behavior
    if not os.path.exists(LOG_FILE):
        _generate_default_log(LOG_FILE)

    # 1. Extract
    d_list, sessions, api_calls = extract_log_data(LOG_FILE)

    # 2. Transform
    error_summary, api_averages = transform_metrics(d_list, api_calls)

    # 3. Load
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    load_data_to_db(DB_PATH, error_summary, api_averages)

    # 4. Generate report
    load_report("report.html", error_summary, api_averages, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
