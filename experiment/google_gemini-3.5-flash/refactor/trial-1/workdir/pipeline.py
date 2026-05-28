"""Pipeline module for processing server logs, storing metrics, and generating reports.

Follows the Extract, Transform, Load (ETL) pattern to securely and cleanly
process log data.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration via Environment Variables with safe defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular Expression Patterns for Log Parsing
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def _parse_info_body(
    dt: str,
    body: str,
    log_entries: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]],
) -> None:
    """Parse INFO level log bodies for user activities or API metrics.

    Args:
        dt: The timestamp of the log.
        body: The main content body of the log line.
        log_entries: Mutable list to append parsed log events.
        api_calls: Mutable list to append parsed API calls.
    """
    user_match = USER_PATTERN.match(body)
    if user_match:
        uid, action = user_match.groups()
        log_entries.append({
            "d": dt,
            "t": "USR",
            "u": uid,
            "a": action.strip(),
        })
        return

    api_match = API_PATTERN.match(body)
    if api_match:
        endpoint, dur = api_match.groups()
        api_calls.append({
            "d": dt,
            "endpoint": endpoint,
            "ms": int(dur) if dur is not None else 0,
        })


def parse_log_line(
    dt: str,
    lvl: str,
    body: str,
    log_entries: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]],
) -> None:
    """Parse parsed standard log line components into respective lists.

    Args:
        dt: The timestamp of the log.
        lvl: The log level (e.g., INFO, ERROR, WARN).
        body: The main content body of the log line.
        log_entries: Mutable list to append parsed log events.
        api_calls: Mutable list to append parsed API calls.
    """
    if lvl == "ERROR":
        log_entries.append({"d": dt, "t": "ERR", "m": body.strip()})
        return
    if lvl == "WARN":
        log_entries.append({"d": dt, "t": "WARN", "m": body.strip()})
        return
    if lvl == "INFO":
        _parse_info_body(dt, body, log_entries, api_calls)


def extract_log_data(
    log_file_path: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract raw log lines from a file and parse them using regex patterns.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        A tuple containing:
            - A list of log entries (errors, warnings, user events).
            - A list of API calls with timestamps and latency durations.
    """
    log_entries: List[Dict[str, Any]] = []
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return log_entries, api_calls

    with open(log_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        match = LOG_LINE_PATTERN.match(line.strip())
        if not match:
            continue
        dt, lvl, body = match.groups()
        parse_log_line(dt, lvl, body, log_entries, api_calls)

    return log_entries, api_calls


def _update_session(
    uid: str, action: str, dt: str, active_sessions: Dict[str, str]
) -> None:
    """Update active user sessions based on login/logout activity.

    Args:
        uid: User identifier.
        action: User action string.
        dt: Timestamp of the event.
        active_sessions: Mutable dictionary representing active sessions.
    """
    if "logged in" in action:
        active_sessions[uid] = dt
        return
    if "logged out" in action and uid in active_sessions:
        active_sessions.pop(uid)


def transform_log_data(
    log_entries: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Transform extracted raw logs and api calls into structured metrics.

    Args:
        log_entries: Raw parsed log entries.
        api_calls: Raw parsed API call records.

    Returns:
        A tuple containing:
            - A dictionary summarizing error counts by error message.
            - A dictionary of API endpoints mapped to lists of durations.
            - A dictionary representing active user sessions.
    """
    errors_summary: Dict[str, int] = {}
    endpoint_stats: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in log_entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            errors_summary[msg] = errors_summary.get(msg, 0) + 1
        elif entry["t"] == "USR":
            _update_session(entry["u"], entry["a"], entry["d"], active_sessions)

    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    return errors_summary, endpoint_stats, active_sessions


def load_metrics_to_db(
    db_path: str,
    errors_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """Load the summarized metrics into the database using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        errors_summary: Counts of error occurrences.
        endpoint_stats: List of latencies per API endpoint.
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

    now_str = str(datetime.datetime.now())

    for msg, count in errors_summary.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now_str, msg, count),
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now_str, ep, avg),
        )

    conn.commit()
    conn.close()


def load_report_to_html(
    report_path: str,
    errors_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Load/write aggregated metrics into a human-readable HTML system report.

    Args:
        report_path: Destination path for the HTML report.
        errors_summary: Counts of error occurrences.
        endpoint_stats: List of latencies per API endpoint.
        active_sessions: Active user sessions representation.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrate the log ETL pipeline execution."""
    log_entries, api_calls = extract_log_data(LOG_FILE)
    errors_summary, endpoint_stats, active_sessions = transform_log_data(
        log_entries, api_calls
    )
    load_metrics_to_db(DB_PATH, errors_summary, endpoint_stats)
    load_report_to_html(
        "report.html", errors_summary, endpoint_stats, active_sessions
    )
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as default_log:
            default_log.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            default_log.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            default_log.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            default_log.write(
                "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            )
            default_log.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            default_log.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
