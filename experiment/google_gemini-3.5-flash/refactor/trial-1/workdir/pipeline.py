"""
Log Ingestion and Analysis Pipeline.

This script extracts data from server log files, processes and aggregates key metrics
(such as error counts, API average latencies, and active user sessions),
persists these records safely into a database, and generates an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration parameters populated from environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT_STR: str = os.getenv("DB_PORT", "5432")
try:
    DB_PORT: int = int(DB_PORT_STR)
except ValueError:
    DB_PORT = 5432
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_data(file_path: str) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], Dict[str, str]]:
    """Extracts raw event and performance data from the log file using regular expressions.

    Args:
        file_path: Path to the log file on disk.

    Returns:
        A tuple of:
        - List of error records containing timestamp 'd' and message 'm'.
        - List of API call records containing timestamp 'd', endpoint name 'endpoint', and duration 'ms'.
        - Dict tracking user login state mapping user ID to timestamp of last login.
    """
    errors: List[Dict[str, str]] = []
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(file_path):
        return errors, api_calls, sessions

    # Standard log line pattern: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
    )
    user_pattern = re.compile(r"User\s+(\S+)\s+(.*)")
    api_pattern = re.compile(r"API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if not match:
                continue

            dt, lvl, message = match.groups()

            if lvl == "ERROR":
                errors.append({"d": dt, "m": message.strip()})
            elif lvl == "INFO":
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
                        ms = int(dur_str) if dur_str else 0
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": ms})

    return errors, api_calls, sessions


def transform_metrics(
    errors: List[Dict[str, str]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """Transforms raw log event data into aggregated metric summaries.

    Args:
        errors: Raw error lists.
        api_calls: Raw api call list records.

    Returns:
        A tuple of:
        - A dictionary of aggregated error message frequencies.
        - A dictionary of average response latency (ms) per API endpoint.
    """
    # Count occurrence frequency of error messages
    error_summary: Dict[str, int] = {}
    for err in errors:
        msg = err["m"]
        error_summary[msg] = error_summary.get(msg, 0) + 1

    # Group response latency times per endpoint to calculate averages
    endpoint_durations: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_durations.setdefault(ep, []).append(call["ms"])

    api_latency_summary: Dict[str, float] = {}
    for ep, times in endpoint_durations.items():
        if times:
            api_latency_summary[ep] = sum(times) / len(times)
        else:
            api_latency_summary[ep] = 0.0

    return error_summary, api_latency_summary


def load_to_database(
    db_path: str, error_summary: Dict[str, int], api_latency_summary: Dict[str, float]
) -> None:
    """Saves the metric summaries into the database using secure parameterized queries.

    Args:
        db_path: Target SQLite database file.
        error_summary: Processed error occurrences mapping.
        api_latency_summary: Calculated API averages mapping.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

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

        # Safely insert aggregated values using query parameters to prevent SQL injection
        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, avg in api_latency_summary.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_summary: Dict[str, int],
    api_latency_summary: Dict[str, float],
    sessions: Dict[str, str],
) -> None:
    """Generates an HTML report summary documenting the analyzed platform metrics.

    Args:
        report_path: Destination path for writing the HTML report file.
        error_summary: Aggregate errors counts.
        api_latency_summary: Evaluated API endpoint speeds.
        sessions: Set of user sessions active at the end of logs execution.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency_summary.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Coordinates and executes the complete ETL process."""
    # Step 1: Extract data from logs
    errors, api_calls, sessions = extract_log_data(LOG_FILE)

    # Step 2: Transform raw records to meaningful aggregates
    error_summary, api_latency_summary = transform_metrics(errors, api_calls)

    # Step 3: Load metrics into SQLite database securely
    load_to_database(DB_PATH, error_summary, api_latency_summary)

    # Step 4: Output metrics into the HTML report
    generate_report("report.html", error_summary, api_latency_summary, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_out:
            f_out.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_out.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_out.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_out.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
