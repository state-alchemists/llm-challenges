import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration retrieved from environment variables with safe defaults
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_logs(file_path: str) -> List[str]:
    """Extracts raw log lines from the specified file.

    Args:
        file_path: The path to the server log file.

    Returns:
        A list of raw log line strings.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_logs(
    lines: List[str]
) -> Tuple[Dict[str, int], Dict[str, float], int]:
    """Transforms raw log lines into structured metrics.

    Uses regex to parse the date, time, log level, and message.
    Extracts error counts, API latency averages, and active session counts.

    Args:
        lines: A list of raw log line strings.

    Returns:
        A tuple containing:
            - A dictionary mapping error messages to their occurrence count.
            - A dictionary mapping API endpoints to their average latency (ms).
            - The count of active user sessions at the end of the log.
    """
    # Regex to parse timestamp, log level, and message from a line
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
    )
    user_pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")
    api_pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?.*$")

    d_list = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    for line in lines:
        line_match = log_pattern.match(line.strip())
        if not line_match:
            continue

        date_str, time_str, lvl, msg = line_match.groups()
        dt = f"{date_str} {time_str}"

        if lvl == "ERROR":
            d_list.append({"d": dt, "t": "ERR", "m": msg.strip()})
            continue

        if lvl == "WARN":
            d_list.append({"d": dt, "t": "WARN", "m": msg.strip()})
            continue

        if lvl != "INFO":
            continue

        user_match = user_pattern.match(msg)
        if user_match:
            uid, action = user_match.groups()
            action = action.strip()
            if "logged in" in action:
                sessions[uid] = dt
            elif "logged out" in action and uid in sessions:
                sessions.pop(uid)
            d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
            continue

        api_match = api_pattern.match(msg)
        if api_match:
            endpoint, dur_str = api_match.groups()
            dur = int(dur_str) if dur_str is not None else 0
            api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
            continue

    # Aggregate errors
    error_counts: Dict[str, int] = {}
    for entry in d_list:
        if entry["t"] == "ERR":
            err_msg = entry["m"]
            error_counts[err_msg] = error_counts.get(err_msg, 0) + 1

    # Aggregate API metrics
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    endpoint_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        endpoint_averages[ep] = sum(times) / len(times)

    active_sessions_count = len(sessions)

    return error_counts, endpoint_averages, active_sessions_count


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_averages: Dict[str, float]
) -> None:
    """Loads aggregated metrics into the SQLite database safely.

    Args:
        db_path: The path to the SQLite database.
        error_counts: Dict of error messages and their counts.
        endpoint_averages: Dict of API endpoints and their average latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    try:
        with conn:
            c = conn.cursor()
            c.execute(
                "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
            )

            now_str = str(datetime.datetime.now())

            for msg, count in error_counts.items():
                c.execute(
                    "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                    (now_str, msg, count)
                )

            for ep, avg in endpoint_averages.items():
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (now_str, ep, avg)
                )
    finally:
        conn.close()


def load_to_html_report(
    report_path: str,
    error_counts: Dict[str, int],
    endpoint_averages: Dict[str, float],
    active_sessions_count: int
) -> None:
    """Generates an HTML report from the parsed metrics.

    Args:
        report_path: The path where the HTML report should be written.
        error_counts: Dict of error messages and their counts.
        endpoint_averages: Dict of API endpoints and their average latencies.
        active_sessions_count: The number of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in endpoint_averages.items():
        out += f"<tr><td>{ep}</td><td>{str(round(avg, 1))}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Executes the complete Extract, Transform, and Load pipeline."""
    # Extract
    lines = extract_logs(LOG_FILE)

    # Transform
    error_counts, endpoint_averages, active_sessions_count = transform_logs(lines)

    # Load
    load_to_database(DB_PATH, error_counts, endpoint_averages)
    load_to_html_report("report.html", error_counts, endpoint_averages, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
