"""Log parsing and metrics collection pipeline.

Extracts data from server logs, transforms it into error and performance metrics,
and loads it into both an SQLite database and an HTML report.
"""

from typing import Any, Dict, List, Tuple, Optional
import datetime
import os
import re
import sqlite3

# Environment-based Configuration
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular Expression Patterns for Parsing
LINE_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)
USER_PATTERN: re.Pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN: re.Pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def _parse_line(
    line: str,
    sessions: Dict[str, str]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse a single log line and update active user sessions.

    Args:
        line: The raw log line string.
        sessions: Active user sessions tracker to be updated in-place.

    Returns:
        A tuple of (parsed_event_dict, api_call_dict).
    """
    match = LINE_PATTERN.match(line.strip())
    if not match:
        return None, None
    dt, lvl, msg = match.groups()

    if lvl == "ERROR":
        return {"d": dt, "t": "ERR", "m": msg}, None
    if lvl == "WARN":
        return {"d": dt, "t": "WARN", "m": msg}, None
    if lvl != "INFO":
        return None, None

    user_match = USER_PATTERN.match(msg)
    if user_match:
        uid, action = user_match.groups()
        if "logged in" in action:
            sessions[uid] = dt
        elif "logged out" in action and uid in sessions:
            sessions.pop(uid)
        return {"d": dt, "t": "USR", "u": uid, "a": action}, None

    api_match = API_PATTERN.match(msg)
    if api_match:
        endpoint, dur_str = api_match.groups()
        dur = int(dur_str) if dur_str else 0
        return None, {"d": dt, "endpoint": endpoint, "ms": dur}

    return None, None


def extract(
    log_file_path: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """Extract raw event data and active session info from log file.

    Args:
        log_file_path: Path to the log file to be parsed.

    Returns:
        A tuple containing:
            - A list of general events (errors, warnings, logins/logouts).
            - A list of API execution metrics.
            - A dictionary tracking active user sessions.
    """
    d_list: List[Dict[str, Any]] = []
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file_path):
        return d_list, api_calls, sessions

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            evt, api = _parse_line(line, sessions)
            if evt:
                d_list.append(evt)
            elif api:
                api_calls.append(api)

    return d_list, api_calls, sessions


def transform(
    d_list: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Transform raw logs into aggregated counts and latency stats.

    Args:
        d_list: List of parsed general event metrics.
        api_calls: List of parsed API execution logs.

    Returns:
        A tuple containing:
            - A dictionary mapping error messages to their counts.
            - A dictionary mapping endpoints to lists of response latencies.
    """
    error_summary: Dict[str, int] = {}
    for event in d_list:
        if event["t"] == "ERR":
            msg = event["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint = call["endpoint"]
        endpoint_stats.setdefault(endpoint, []).append(call["ms"])

    return error_summary, endpoint_stats


def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]]
) -> None:
    """Load transformed summary statistics into SQLite.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Aggregated count of each unique error.
        endpoint_stats: API latency logs mapped by endpoint.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    now_str = str(datetime.datetime.now())
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now_str, msg, count))

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now_str, ep, avg))

    conn.commit()
    conn.close()


def generate_report(
    report_path: str,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    sessions: Dict[str, str]
) -> None:
    """Write system analysis report in HTML format.

    Args:
        report_path: Destined path for HTML file.
        error_summary: Aggregated count of unique errors.
        endpoint_stats: API latency records.
        sessions: Active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Execute the pipeline from end-to-end to process data and generate report."""
    # 1. Extract
    d_list, api_calls, sessions = extract(LOG_FILE)

    # 2. Transform
    error_summary, endpoint_stats = transform(d_list, api_calls)

    # 3. Load
    load_to_database(DB_PATH, error_summary, endpoint_stats)
    generate_report("report.html", error_summary, endpoint_stats, sessions)

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
    proc_data()
