"""
Log parsing and metrics reporting pipeline.

Processes server log files to extract and aggregate system errors, API latency,
and active user sessions, storing the metrics in a SQLite database and
generating an HTML report.
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any

# Environment-based Configuration
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
# Note: The fallback password is provided via os.getenv to keep it secure
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_data(
    log_file_path: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extract raw events, sessions, and API calls from the server log file.

    Reads the log file line by line and parses each line using regular expressions.

    Args:
        log_file_path: The filesystem path to the log file.

    Returns:
        A tuple containing:
            - d_list: A list of dicts representing raw events (ERR, USR, WARN).
            - sessions: A dict of active user sessions mapping uid to login datetime.
            - api_calls: A list of dicts representing parsed API latency logs.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return d_list, sessions, api_calls

    # Regex patterns for robust parsing
    line_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
    )
    user_pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")
    api_pattern = re.compile(r"API\s+(\S+)")
    duration_pattern = re.compile(r"took\s+(\d+)ms")

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_match = line_pattern.match(line.strip())
            if not line_match:
                continue

            dt = line_match.group(1)
            lvl = line_match.group(2)
            msg = line_match.group(3)

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": msg.strip()})

            elif lvl == "INFO" and "User" in msg:
                user_match = user_pattern.match(msg)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})

            elif lvl == "INFO" and "API" in msg:
                api_match = api_pattern.search(msg)
                if api_match:
                    endpoint = api_match.group(1)
                    dur_match = duration_pattern.search(msg)
                    dur = dur_match.group(1) if dur_match else "0"
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": int(dur)})

            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": msg.strip()})

    return d_list, sessions, api_calls


def transform_metrics(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """
    Transform and aggregate raw extracted log metrics.

    Args:
        d_list: List of raw parsed log events.
        api_calls: List of parsed API calls.

    Returns:
        A tuple containing:
            - error_counts: Dict mapping error messages to occurrence counts.
            - api_averages: Dict mapping API endpoints to average latency in ms.
    """
    error_counts: Dict[str, int] = {}
    for x in d_list:
        if x.get("t") == "ERR":
            msg = x["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        api_averages[ep] = sum(times) / len(times) if times else 0.0

    return error_counts, api_averages


def load_data_to_db(
    db_path: str, error_counts: Dict[str, int], api_averages: Dict[str, float]
) -> None:
    """
    Load aggregated metrics into the SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Aggregated error counts.
        api_averages: Aggregated average API latencies.
    """
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
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)", (now_str, msg, count)
            )

        for ep, avg in api_averages.items():
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)", (now_str, ep, avg)
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_session_count: int,
) -> None:
    """
    Generate an HTML report showcasing the aggregated metrics.

    Args:
        report_path: Path where the HTML report will be saved.
        error_counts: Aggregated error counts.
        api_averages: Aggregated average API latencies.
        active_session_count: Number of active user sessions.
    """
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
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """
    Main orchestrator of the ETL pipeline.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    d_list, sessions, api_calls = extract_log_data(LOG_FILE)

    # Transform
    error_counts, api_averages = transform_metrics(d_list, api_calls)

    # Load
    load_data_to_db(DB_PATH, error_counts, api_averages)

    # Generate Report
    generate_report("report.html", error_counts, api_averages, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # If log file doesn't exist, seed it with sample logs for verification
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_out:
            f_out.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_out.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_out.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_out.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
