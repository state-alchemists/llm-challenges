"""
Pipeline Refactored Script

This script processes server logs using the Extract-Transform-Load (ETL) pattern,
performing secure parameterized SQL database operations, robust regular expression
log parsing, and generating a clear system report in HTML format.
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any


def extract_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts raw log file data and parses each line using regular expressions.

    Args:
        log_file_path: The filesystem path to the server log file.

    Returns:
        A tuple of (d_list, sessions, api_calls) where:
        - d_list: List of dictionaries of extracted log entries (errors, user logins, etc.).
        - sessions: Dictionary of active user sessions (user_id -> timestamp).
        - api_calls: List of dictionaries representing API calls with their endpoint and latency.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return d_list, sessions, api_calls

    # Regex patterns for line-by-line parsing
    log_pattern: re.Pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$"
    )
    user_pattern: re.Pattern = re.compile(r"^User\s+(\S+)\s+(.+)$")
    api_pattern: re.Pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str: str = line.strip()
            if not line_str:
                continue

            match = log_pattern.match(line_str)
            if not match:
                continue

            dt: str = match.group(1)
            lvl: str = match.group(2)
            msg: str = match.group(3)

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": msg})

            elif lvl == "INFO" and "User" in msg:
                user_match = user_pattern.match(msg)
                if user_match:
                    uid: str = user_match.group(1)
                    action: str = user_match.group(2)
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})

            elif lvl == "INFO" and "API" in msg:
                api_match = api_pattern.match(msg)
                if api_match:
                    endpoint: str = api_match.group(1)
                    dur_str: str = api_match.group(2) if api_match.group(2) else "0"
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": int(dur_str)})

            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": msg})

    return d_list, sessions, api_calls


def transform_data(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Transforms extracted log structures into aggregated metrics.

    Args:
        d_list: Parsed raw logs containing error and warning messages.
        api_calls: Log entries of API calls.

    Returns:
        A tuple of (errors, api_metrics) where:
        - errors: Dict mapping each unique error message to its occurrence count.
        - api_metrics: Dict mapping API endpoints to their average latency (ms).
    """
    errors: Dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg: str = x["m"]
            errors[msg] = errors.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep: str = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_metrics: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        avg: float = sum(times) / len(times)
        api_metrics[ep] = avg

    return errors, api_metrics


def load_data(
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
    errors: Dict[str, int],
    api_metrics: Dict[str, float],
    active_sessions_count: int,
    report_path: str = "report.html",
) -> None:
    """
    Loads statistics into the database (parameterized) and renders the HTML report.

    Args:
        db_path: Target path to the SQLite metrics database.
        db_host: Database hostname (printed for mock connection feedback).
        db_port: Database port (printed for mock connection feedback).
        db_user: Database user (printed for mock connection feedback).
        errors: Aggregated error metrics.
        api_metrics: Aggregated API latency metrics.
        active_sessions_count: Current count of active user sessions.
        report_path: Filesystem path where the report.html output is saved.
    """
    print("Connecting to " + db_host + ":" + str(db_port) + " as " + db_user + "...")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    now_str: str = str(datetime.datetime.now())

    for msg, count in errors.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now_str, msg, count)
        )

    for ep, avg in api_metrics.items():
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now_str, ep, avg)
        )

    conn.commit()
    conn.close()

    out: str = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += "<li><b>" + err_msg + "</b>: " + str(count) + " occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_metrics.items():
        out += "<tr><td>" + ep + "</td><td>" + str(round(avg, 1)) + "</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>" + str(active_sessions_count) + " user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """
    Orchestrates the entire ETL pipeline process.
    """
    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port_str: str = os.getenv("DB_PORT", "5432")
    db_port: int = int(db_port_str) if db_port_str.isdigit() else 5432
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")

    # If the default server.log doesn't exist, create it
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    d_list, sessions, api_calls = extract_data(log_file)

    # Transform
    errors, api_metrics = transform_data(d_list, api_calls)

    # Load
    load_data(
        db_path=db_path,
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
        errors=errors,
        api_metrics=api_metrics,
        active_sessions_count=len(sessions),
        report_path="report.html",
    )

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    main()
