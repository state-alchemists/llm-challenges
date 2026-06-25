"""Pipeline for processing server logs and generating system report.

This script parses server logs, loads metrics to a database securely, and
generates an HTML report summarizing errors, API latency, and active sessions.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List

# Configuration constants from environment variables
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_PATH = os.getenv("DB_PATH", "metrics.db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_logs(file_path: str) -> List[Dict[str, Any]]:
    """Extract and parse entries from the log file using regular expressions.

    Args:
        file_path: Path to the server log file.

    Returns:
        A list of parsed log records containing timestamp, level, and message.
    """
    records: List[Dict[str, Any]] = []
    if not os.path.exists(file_path):
        return records

    # Regex to match general log structure: [date] [time] [level] [message]
    log_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>[A-Z]+)\s+(?P<message>.*)$"
    )

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = log_pattern.match(line)
            if not match:
                continue

            gd = match.groupdict()
            records.append({
                "timestamp": gd["timestamp"],
                "level": gd["level"],
                "message": gd["message"]
            })

    return records


def _process_user_log(
    msg: str,
    dt: str,
    active_sessions: Dict[str, str],
    pattern: re.Pattern,
) -> None:
    """Process user login and logout events.

    Args:
        msg: Raw log message.
        dt: Datetime string.
        active_sessions: Dict of active user sessions.
        pattern: Regex pattern to match user log info.
    """
    user_match = pattern.match(msg)
    if not user_match:
        return
    uid = user_match.group("uid")
    action = user_match.group("action").strip()
    if "logged in" in action:
        active_sessions[uid] = dt
    elif "logged out" in action:
        active_sessions.pop(uid, None)


def _process_api_log(
    msg: str,
    api_metrics: Dict[str, List[int]],
    pattern: re.Pattern,
) -> None:
    """Process API call latency events.

    Args:
        msg: Raw log message.
        api_metrics: Dict mapping endpoints to latency lists.
        pattern: Regex pattern to match API log info.
    """
    api_match = pattern.match(msg)
    if not api_match:
        return
    endpoint = api_match.group("endpoint")
    dur_str = api_match.group("ms")
    dur = int(dur_str) if dur_str is not None else 0
    api_metrics.setdefault(endpoint, []).append(dur)


def transform_logs(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transform raw log records into structured metrics for errors, API, and sessions.

    Args:
        records: Raw log records.

    Returns:
        A dictionary containing:
            - "error_counts": Dict[str, int] mapping error messages to their occurrences.
            - "api_metrics": Dict[str, List[int]] mapping endpoints to lists of latencies.
            - "active_sessions": Dict[str, str] mapping user IDs to their login timestamps.
    """
    error_counts: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    user_pattern = re.compile(r"^User (?P<uid>\S+)\s+(?P<action>.*)$")
    api_pattern = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?")

    for rec in records:
        lvl = rec["level"]
        dt = rec["timestamp"]
        msg = rec["message"]

        if lvl == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1
            continue

        if lvl != "INFO":
            continue

        if "User" in msg:
            _process_user_log(msg, dt, active_sessions, user_pattern)
        elif "API" in msg:
            _process_api_log(msg, api_metrics, api_pattern)

    return {
        "error_counts": error_counts,
        "api_metrics": api_metrics,
        "active_sessions": active_sessions,
    }


def load_to_db(
    db_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
) -> None:
    """Save the aggregated metrics securely into the SQLite database.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Dictionary mapping error messages to occurrences.
        api_metrics: Dictionary mapping endpoints to latency measurements.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        # Parameterized insertion for errors
        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        # Parameterized insertion for API metrics
        for ep, times in api_metrics.items():
            if not times:
                continue
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Generate report.html with errors, API latency, and active session count.

    Args:
        report_path: Path to write the output HTML report.
        error_counts: Extracted error messages and counts.
        api_metrics: Extracted API metrics.
        active_sessions: Dictionary of currently active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Run the main ETL pipeline processing server logs."""
    # 1. Extract
    records = extract_logs(LOG_FILE)

    # 2. Transform
    metrics = transform_logs(records)

    # 3. Load to DB and Report
    load_to_db(DB_PATH, metrics["error_counts"], metrics["api_metrics"])
    generate_report(
        "report.html",
        metrics["error_counts"],
        metrics["api_metrics"],
        metrics["active_sessions"],
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as file:
            file.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            file.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            file.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            file.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            file.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            file.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
