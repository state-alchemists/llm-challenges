"""Pipeline for processing server logs and generating system reports.

This module extracts log entries from server logs, transforms them into
aggregated metrics (error counts, API latencies, active sessions), and
loads the results into a database and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any

# Configuration using environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular expression patterns for log parsing
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def extract_log_data(
    log_file_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Extract and parse log entries from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of general parsed log entries (errors, warnings, user events).
            - A list of API metrics logs.
            - A dictionary tracking active user sessions (user_id -> login_time).
    """
    d_list: list[dict[str, Any]] = []
    api_calls: list[dict[str, Any]] = []
    sessions: dict[str, str] = {}

    if not os.path.exists(log_file_path):
        return d_list, api_calls, sessions

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_LINE_PATTERN.match(line.strip())
            if not match:
                continue

            dt: str = match.group(1)
            lvl: str = match.group(2)
            detail: str = match.group(3)

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": detail.strip()})

            elif lvl == "INFO":
                user_match = USER_PATTERN.match(detail)
                if user_match:
                    uid: str = user_match.group(1)
                    action: str = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                else:
                    api_match = API_PATTERN.match(detail)
                    if api_match:
                        endpoint: str = api_match.group(1)
                        dur_str: str | None = api_match.group(2)
                        dur: int = int(dur_str) if dur_str else 0
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})

            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": detail.strip()})

    return d_list, api_calls, sessions


def transform_log_data(
    d_list: list[dict[str, Any]],
    api_calls: list[dict[str, Any]],
    sessions: dict[str, str],
) -> tuple[dict[str, int], dict[str, float], int]:
    """Transform raw log entries into aggregated metrics.

    Args:
        d_list: General parsed log entries.
        api_calls: API metrics logs.
        sessions: Active user sessions.

    Returns:
        A tuple containing:
            - A dictionary of error message counts.
            - A dictionary of average API latencies per endpoint.
            - The count of currently active sessions.
    """
    error_counts: dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg: str = x["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    api_latency_raw: dict[str, list[int]] = {}
    for call in api_calls:
        ep: str = call["endpoint"]
        api_latency_raw.setdefault(ep, []).append(call["ms"])

    api_latency_avg: dict[str, float] = {}
    for ep, times in api_latency_raw.items():
        if times:
            api_latency_avg[ep] = sum(times) / len(times)
        else:
            api_latency_avg[ep] = 0.0

    session_count: int = len(sessions)

    return error_counts, api_latency_avg, session_count


def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Load aggregated metrics into the SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Dictionary of error counts to insert.
        api_latency: Dictionary of average API latencies per endpoint to insert.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Insert error counts
    for msg, count in error_counts.items():
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now_str, msg, count),
        )

    # Insert API latency metrics
    for ep, avg in api_latency.items():
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now_str, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    report_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    session_count: int,
) -> None:
    """Generate an HTML system report and write it to disk.

    Args:
        report_path: Path to the HTML file to be generated.
        error_counts: Dictionary of error counts.
        api_latency: Dictionary of average API latencies.
        session_count: Count of currently active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += "<li><b>" + err_msg + "</b>: " + str(count) + " occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency.items():
        out += "<tr><td>" + ep + "</td><td>" + str(round(avg, 1)) + "</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>" + str(session_count) + " user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Run the ETL pipeline using config from environment variables."""
    print("Connecting to " + DB_HOST + ":" + str(DB_PORT) + " as " + DB_USER + "...")

    # Extract
    d_list, api_calls, sessions = extract_log_data(LOG_FILE)

    # Transform
    error_counts, api_latency, session_count = transform_log_data(
        d_list, api_calls, sessions
    )

    # Load Database
    load_to_database(DB_PATH, error_counts, api_latency)

    # Load/Generate Report
    generate_report("report.html", error_counts, api_latency, session_count)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_log:
            f_log.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_log.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_log.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_log.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
