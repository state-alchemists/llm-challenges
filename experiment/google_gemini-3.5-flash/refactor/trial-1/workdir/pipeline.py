"""Pipeline module for processing server logs and generating report."""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple

# Configuration via environment variables with original fallbacks
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")

# Regular expressions for log line parsing
# Matches log pattern: <date> <time> <LEVEL> <message>
LOG_LINE_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
# Matches user interaction within INFO message
USER_ACTION_PATTERN: re.Pattern = re.compile(
    r"^User\s+(\S+)\s+(.*)$"
)
# Matches API metrics within INFO message
API_METRIC_PATTERN: re.Pattern = re.compile(
    r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?"
)


def extract_log_lines(file_path: str) -> List[str]:
    """Read and extract all raw lines from the log file.

    Args:
        file_path (str): The file path of the log file to read.

    Returns:
        List[str]: A list of raw string lines from the log file.
            If the file does not exist, returns an empty list.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_log_data(
    lines: List[str],
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Parse log lines and transform them into aggregated data structures.

    Analyzes error counts, API latencies, and tracks user sessions.

    Args:
        lines (List[str]): A list of raw lines from the log file.

    Returns:
        Tuple[Dict[str, int], Dict[str, List[int]], int]: A tuple containing:
            - Dict[str, int]: A mapping of error messages to their counts.
            - Dict[str, List[int]]: A mapping of API endpoints
              to their recorded durations.
            - int: The count of user sessions that are currently active.
    """
    error_counts: Dict[str, int] = {}
    endpoint_stats: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for line in lines:
        match = LOG_LINE_PATTERN.match(line.strip())
        if not match:
            continue

        dt, lvl, msg = match.groups()

        if lvl == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif lvl == "INFO":
            # Check user interaction
            user_match = USER_ACTION_PATTERN.match(msg)
            if user_match:
                uid, action = user_match.groups()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)

            # Check API metric
            api_match = API_METRIC_PATTERN.match(msg)
            if api_match:
                endpoint = api_match.group(1)
                dur_str = api_match.group(2)
                dur = int(dur_str) if dur_str is not None else 0
                endpoint_stats.setdefault(endpoint, []).append(dur)

    return error_counts, endpoint_stats, len(sessions)


def load_to_database(
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """Save the calculated error and API metrics to the database.

    Args:
        error_counts (Dict[str, int]): Aggregated error messages
            and counts.
        endpoint_stats (Dict[str, List[int]]): Mapping of API
            endpoints to lists of durations.
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

        # Insert errors using parameterized query
        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        # Insert API metrics using parameterized query
        for ep, times in endpoint_stats.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics "
                "(dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_to_report(
    report_path: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
) -> None:
    """Generate the HTML report and save it to the specified file.

    Args:
        report_path (str): The file path where the report should be saved.
        error_counts (Dict[str, int]): Mapping of error messages
            to counts.
        endpoint_stats (Dict[str, List[int]]): Mapping of API
            endpoints to lists of latency values.
        active_sessions_count (int): Count of currently active
            user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"Job finished at {datetime.datetime.now()}")


def proc_data() -> None:
    """Run the complete pipeline."""
    # 1. Extract
    lines = extract_log_lines(LOG_FILE)

    # 2. Transform
    res = transform_log_data(lines)
    error_counts, endpoint_stats, active_sessions_count = res

    # 3. Load
    load_to_database(error_counts, endpoint_stats)
    load_to_report(
        "report.html",
        error_counts,
        endpoint_stats,
        active_sessions_count,
    )


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as dummy_f:
            dummy_f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            dummy_f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            dummy_f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            dummy_f.write(
                "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            )
            dummy_f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            dummy_f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
