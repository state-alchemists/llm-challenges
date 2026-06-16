"""Pipeline for processing server logs, storing metrics, and generating reports."""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration retrieved safely from environment variables with defaults.
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regex pattern for overall log line parsing (Timestamp, Level, Message)
LOG_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$")

# Regex pattern for extracting user activities
USER_ACTION_RE = re.compile(r"^User\s+(\S+)\s+(.*)$")

# Regex pattern for extracting API endpoint metrics
API_CALL_RE = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?.*$")


def extract_log_data(
    log_file_path: str,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[Dict[str, str]]]:
    """Reads the log file and extracts structured log events using regex.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        A tuple containing:
            - list of parsed error/warning records
            - list of parsed API latency metrics
            - list of parsed user activities
    """
    errors_and_warns: List[Dict[str, str]] = []
    api_calls: List[Dict[str, Any]] = []
    user_activities: List[Dict[str, str]] = []

    if not os.path.exists(log_file_path):
        return errors_and_warns, api_calls, user_activities

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            dt, lvl, msg = match.groups()

            if lvl == "ERROR":
                errors_and_warns.append(
                    {"dt": dt, "type": "ERR", "message": msg.strip()}
                )
            elif lvl == "WARN":
                errors_and_warns.append(
                    {"dt": dt, "type": "WARN", "message": msg.strip()}
                )
            elif lvl == "INFO":
                user_match = USER_ACTION_RE.match(msg)
                if user_match:
                    uid, action = user_match.groups()
                    user_activities.append(
                        {"dt": dt, "uid": uid, "action": action.strip()}
                    )
                    continue

                api_match = API_CALL_RE.match(msg)
                if api_match:
                    endpoint, dur_str = api_match.groups()
                    ms = int(dur_str) if dur_str else 0
                    api_calls.append({"dt": dt, "endpoint": endpoint, "ms": ms})

    return errors_and_warns, api_calls, user_activities


def transform_log_data(
    errors_and_warns: List[Dict[str, str]],
    api_calls: List[Dict[str, Any]],
    user_activities: List[Dict[str, str]],
) -> Tuple[Dict[str, int], Dict[str, float], int]:
    """Transforms raw log events into aggregate statistics.

    Calculates error occurrence counts, average API response latencies, and total active user sessions.

    Args:
        errors_and_warns: Parsed error/warning log events.
        api_calls: Parsed API latency metrics.
        user_activities: Parsed user activity events.

    Returns:
        A tuple containing:
            - error message frequency count map
            - API endpoint latency average map
            - active user session count
    """
    # Calculate error occurrence frequencies
    error_counts: Dict[str, int] = {}
    for item in errors_and_warns:
        if item["type"] == "ERR":
            msg = item["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    # Calculate average API response latencies per endpoint
    endpoint_durations: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint = call["endpoint"]
        endpoint_durations.setdefault(endpoint, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for endpoint, durations in endpoint_durations.items():
        if durations:
            api_averages[endpoint] = sum(durations) / len(durations)

    # Compute active sessions tracking logins/logouts
    sessions: Dict[str, str] = {}
    for act in user_activities:
        uid = act["uid"]
        action = act["action"]
        dt = act["dt"]
        if "logged in" in action:
            sessions[uid] = dt
        elif "logged out" in action and uid in sessions:
            sessions.pop(uid)

    return error_counts, api_averages, len(sessions)


def load_data_and_generate_report(
    db_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions_count: int,
) -> None:
    """Saves metrics to database securely and generates system report HTML.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Dictionary of error frequencies.
        api_averages: Dictionary of average latency per endpoint.
        active_sessions_count: Number of currently active user sessions.
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

        # Parameterized queries to eliminate SQL injection
        for msg, count in error_counts.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now_str, msg, count))

        for ep, avg in api_averages.items():
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now_str, ep, avg))

        conn.commit()
    finally:
        conn.close()

    # Create HTML report
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
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

    with open("report.html", "w", encoding="utf-8") as f:
        f.write(out)

    print(f"Job finished at {datetime.datetime.now()}")


def proc_data() -> None:
    """Orchestrates the entire ETL processing pipeline."""
    # 1. Extract log information
    errors_and_warns, api_calls, user_activities = extract_log_data(LOG_FILE)

    # 2. Transform raw events into summary metrics
    error_counts, api_averages, active_sessions_count = transform_log_data(
        errors_and_warns, api_calls, user_activities
    )

    # 3. Load structured statistics and publish report
    load_data_and_generate_report(
        DB_PATH, error_counts, api_averages, active_sessions_count
    )


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
