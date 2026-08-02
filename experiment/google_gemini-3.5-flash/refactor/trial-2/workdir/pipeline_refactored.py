"""Pipeline for processing server logs and generating a report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Set, Tuple


# Configuration from environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_logs(log_file_path: str) -> List[Tuple[str, str, str]]:
    """Reads and extracts fields from the server log file.

    Args:
        log_file_path: Path to the log file.

    Returns:
        A list of tuples containing (timestamp, level, message) for each log line.
    """
    if not os.path.exists(log_file_path):
        return []

    parsed_lines: List[Tuple[str, str, str]] = []
    # Regex to parse the timestamp, log level, and the log message
    line_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
    )

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = line_pattern.match(line)
            if match:
                dt = match.group(1)
                lvl = match.group(2)
                msg = match.group(3)
                parsed_lines.append((dt, lvl, msg))

    return parsed_lines


def transform_logs(
    parsed_lines: List[Tuple[str, str, str]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Transforms raw log data into metrics for error, API, and session tracking.

    Args:
        parsed_lines: List of tuples containing (timestamp, level, message).

    Returns:
        A tuple containing:
            1. Dictionary of error messages and their occurrence counts.
            2. Dictionary of API endpoints and lists of latency durations (ms).
            3. Dictionary of active session users and their last login timestamp.
    """
    error_counts: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    user_pattern = re.compile(r"User\s+(\S+)\s+(.*)")
    api_pattern = re.compile(r"API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    for dt, lvl, message in parsed_lines:
        lvl_upper = lvl.upper()
        if lvl_upper == "ERROR":
            error_counts[message] = error_counts.get(message, 0) + 1

        elif lvl_upper == "INFO":
            if "User" in message:
                user_match = user_pattern.search(message)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)

            elif "API" in message:
                api_match = api_pattern.search(message)
                if api_match:
                    endpoint = api_match.group(1)
                    dur_str = api_match.group(2)
                    dur = int(dur_str) if dur_str else 0
                    api_metrics.setdefault(endpoint, []).append(dur)

    return error_counts, api_metrics, sessions


def load_to_db(
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
) -> None:
    """Saves metrics to the database using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        db_host: Database host (for connection status printout).
        db_port: Database port (for connection status printout).
        db_user: Database user (for connection status printout).
        error_counts: Dictionary of error messages and their counts.
        api_metrics: Dictionary of API endpoints and lists of latencies.
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

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

        for msg, count in error_counts.items():
            # Use safe parameterized query to prevent SQL Injection
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in api_metrics.items():
            if times:
                avg = sum(times) / len(times)
                # Use safe parameterized query to prevent SQL Injection
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    sessions: Dict[str, str],
) -> None:
    """Generates an HTML report summarizing log processing findings.

    Args:
        report_path: Target path for writing the HTML report.
        error_counts: Dictionary of error messages and their counts.
        api_metrics: Dictionary of API endpoints and lists of latencies.
        sessions: Dictionary of active session users.
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
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Executes the full pipeline process from Extraction to Loading."""
    parsed_lines = extract_logs(LOG_FILE)
    error_counts, api_metrics, sessions = transform_logs(parsed_lines)

    load_to_db(
        db_path=DB_PATH,
        db_host=DB_HOST,
        db_port=DB_PORT,
        db_user=DB_USER,
        error_counts=error_counts,
        api_metrics=api_metrics,
    )

    generate_report(
        report_path="report.html",
        error_counts=error_counts,
        api_metrics=api_metrics,
        sessions=sessions,
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as file_handle:
            file_handle.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            file_handle.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            file_handle.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            file_handle.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            file_handle.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            file_handle.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
