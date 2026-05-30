"""Pipeline script to process server logs, insert metrics into DB, and generate reports."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration using environment variables with defaults
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_FILE = "report.html"

# Precompiled Regex patterns for robust log parsing
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(INFO|ERROR|WARN|DEBUG)\s+(.*)$"
)
USER_ACTION_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_CALL_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def extract_log_data(log_file_path: str) -> List[Dict[str, str]]:
    """Extracts raw log lines matching the standard log format.

    Args:
        log_file_path: The file path to the server logs.

    Returns:
        A list of parsed log dictionaries containing dt, lvl, and msg.
    """
    if not os.path.exists(log_file_path):
        return []

    entries: List[Dict[str, str]] = []
    with open(log_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        match = LOG_LINE_PATTERN.match(line.strip())
        if not match:
            continue
        dt, lvl, msg = match.groups()
        entries.append({"dt": dt, "lvl": lvl, "msg": msg})

    return entries


def _process_info_entry(
    dt: str,
    msg: str,
    sessions: Dict[str, str],
    api_calls: List[Dict[str, Any]],
) -> None:
    """Helper to process INFO log lines for user sessions or API latency.

    Args:
        dt: The timestamp of the log entry.
        msg: The message portion of the INFO log entry.
        sessions: Mutable dictionary of active user sessions.
        api_calls: Mutable list of parsed API call metrics.
    """
    user_match = USER_ACTION_PATTERN.match(msg)
    if user_match:
        uid, action = user_match.groups()
        if "logged in" in action:
            sessions[uid] = dt
        elif "logged out" in action:
            sessions.pop(uid, None)
        return

    api_match = API_CALL_PATTERN.match(msg)
    if api_match:
        endpoint, dur_str = api_match.groups()
        ms = int(dur_str) if dur_str is not None else 0
        api_calls.append({"dt": dt, "endpoint": endpoint, "ms": ms})


def transform_log_entries(
    entries: List[Dict[str, str]]
) -> Tuple[Dict[str, int], List[Dict[str, Any]], Dict[str, str]]:
    """Transforms raw log entries into errors, API latency logs, and sessions.

    Args:
        entries: Raw log dictionaries.

    Returns:
        A tuple of (error_counts, api_calls, active_sessions).
    """
    error_counts: Dict[str, int] = {}
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    for entry in entries:
        lvl = entry["lvl"]
        dt = entry["dt"]
        msg = entry["msg"]

        if lvl == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif lvl == "INFO":
            _process_info_entry(dt, msg, sessions, api_calls)

    return error_counts, api_calls, sessions


def calculate_api_stats(api_calls: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculates average latency for each endpoint.

    Args:
        api_calls: A list of dicts representing raw API calls.

    Returns:
        A dictionary mapping endpoints to their average latencies in ms.
    """
    endpoint_totals: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_totals.setdefault(call["endpoint"], []).append(call["ms"])

    stats: Dict[str, float] = {}
    for endpoint, times in endpoint_totals.items():
        if times:
            stats[endpoint] = sum(times) / len(times)
    return stats


def load_metrics_to_db(
    error_counts: Dict[str, int],
    api_stats: Dict[str, float],
) -> None:
    """Inserts aggregated metrics into the database using parameterized queries.

    Args:
        error_counts: Dictionary of error messages and their counts.
        api_stats: Dictionary of endpoints and their average latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, avg in api_stats.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    error_counts: Dict[str, int],
    api_stats: Dict[str, float],
    active_sessions_count: int,
) -> None:
    """Generates an HTML report summarizing the extracted metrics.

    Args:
        error_counts: Dictionary of error messages and their counts.
        api_stats: Dictionary of endpoints and their average latencies.
        active_sessions_count: Total number of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrates the log parsing, metric transformation, loading, and reporting."""
    # Ensure default logs exist if LOG_FILE is missing
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # 1. Extract log data
    raw_entries = extract_log_data(LOG_FILE)

    # 2. Transform raw log data into metrics
    error_counts, api_calls, sessions = transform_log_entries(raw_entries)
    api_stats = calculate_api_stats(api_calls)

    # 3. Load metrics into SQLite Database
    load_metrics_to_db(error_counts, api_stats)

    # 4. Generate the final HTML report
    generate_html_report(error_counts, api_stats, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    proc_data()
