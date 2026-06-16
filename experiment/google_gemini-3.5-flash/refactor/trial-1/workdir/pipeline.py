"""Log processing and report generation pipeline.

This module extracts server log information, transforms it into structured formats,
stores the metrics in a SQLite database, and generates an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration retrieved from environment variables with sensible defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
# Default password retrieved from env var safely to avoid hardcoded secrets in version control
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_data(log_file_path: str) -> List[str]:
    """Reads raw lines from the log file.

    Args:
        log_file_path (str): The path to the log file to read.

    Returns:
        List[str]: A list of raw log lines.
    """
    if not os.path.exists(log_file_path):
        return []
    with open(log_file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_log_data(
    lines: List[str]
) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, Any]]]:
    """Parses raw log lines using regular expressions.

    Processes date-time, level, and message content. Tracks active user sessions
    and extracts API metrics and error summaries.

    Args:
        lines (List[str]): A list of raw log lines.

    Returns:
        Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, Any]]]:
            A tuple containing:
            - d_list (List[Dict[str, str]]): List of parsed log entries.
            - sessions (Dict[str, str]): Dict mapping active user ID to login timestamp.
            - api_calls (List[Dict[str, Any]]): List of API metric dictionaries.
    """
    d_list: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    # Regex patterns for parsing log prefix, user, and API details
    log_pattern = re.compile(
        r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<lvl>INFO|ERROR|WARN) (?P<msg>.*)$"
    )
    user_pattern = re.compile(r"^User (?P<uid>\S+)\s+(?P<action>.*)$")
    api_pattern = re.compile(r"^API (?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?")

    for line in lines:
        line_stripped = line.strip()
        match = log_pattern.match(line_stripped)
        if not match:
            continue

        dt = match.group("dt")
        lvl = match.group("lvl")
        msg = match.group("msg")

        if lvl == "ERROR":
            d_list.append({"d": dt, "t": "ERR", "m": msg.strip()})

        elif lvl == "INFO":
            match_user = user_pattern.match(msg)
            if match_user:
                uid = match_user.group("uid")
                action = match_user.group("action").strip()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
                d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
            else:
                match_api = api_pattern.match(msg)
                if match_api:
                    endpoint = match_api.group("endpoint")
                    dur_str = match_api.group("dur")
                    dur = int(dur_str) if dur_str else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})

        elif lvl == "WARN":
            d_list.append({"d": dt, "t": "WARN", "m": msg.strip()})

    return d_list, sessions, api_calls


def load_data_to_db(
    db_path: str,
    d_list: List[Dict[str, str]],
    api_calls: List[Dict[str, Any]],
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Loads transformed metrics into the SQLite database.

    Saves error messages and API endpoints metrics using parameterized queries
    to prevent SQL injection, and returns aggregated stats for reporting.

    Args:
        db_path (str): Path to the SQLite database.
        d_list (List[Dict[str, str]]): List of parsed log entries.
        api_calls (List[Dict[str, Any]]): List of API call details.

    Returns:
        Tuple[Dict[str, int], Dict[str, List[int]]]:
            A tuple containing:
            - error_summary (Dict[str, int]): Map of error message to occurrence count.
            - endpoint_stats (Dict[str, List[int]]): Map of endpoint to lists of latency times.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    error_summary: Dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    now_str = str(datetime.datetime.now())

    for msg, count in error_summary.items():
        # Parameterized query to avoid SQL injection
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now_str, msg, count)
        )

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        # Parameterized query to avoid SQL injection
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now_str, ep, avg)
        )

    conn.commit()
    conn.close()

    return error_summary, endpoint_stats


def generate_report(
    report_path: str,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
) -> None:
    """Generates an HTML report summarizing errors, API latency, and active sessions.

    Args:
        report_path (str): The file path where report will be saved.
        error_summary (Dict[str, int]): Dictionary of error messages and occurrence counts.
        endpoint_stats (Dict[str, List[int]]): Dictionary of API endpoints and lists of latency times.
        active_sessions_count (int): Count of currently active user sessions.
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

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrates the entire log processing pipeline.

    Loads, transforms, saves metrics to database, and generates the report.
    """
    raw_lines = extract_log_data(LOG_FILE)
    d_list, sessions, api_calls = transform_log_data(raw_lines)
    error_summary, endpoint_stats = load_data_to_db(DB_PATH, d_list, api_calls)
    generate_report("report.html", error_summary, endpoint_stats, len(sessions))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fixture_f:
            fixture_f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fixture_f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fixture_f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fixture_f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fixture_f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fixture_f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
