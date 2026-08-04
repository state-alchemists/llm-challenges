import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def _parse_info_message(
    message: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Parses an INFO log line message.

    Args:
        message: The message body of the INFO log line.

    Returns:
        A tuple of (user_id, action, endpoint, api_duration).
    """
    user_match = USER_PATTERN.match(message)
    if user_match:
        uid, action = user_match.groups()
        return uid, action.strip(), None, None

    api_match = API_PATTERN.match(message)
    if api_match:
        endpoint, dur_str = api_match.groups()
        dur = int(dur_str) if dur_str is not None else 0
        return None, None, endpoint, dur

    return None, None, None, None


def extract_log_data(
    log_file_path: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """Extracts and parses data from the log file using regular expressions.

    Args:
        log_file_path: The filesystem path to the log file.

    Returns:
        A tuple of (d_list, api_calls, sessions).
    """
    d_list: List[Dict[str, Any]] = []
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file_path):
        return d_list, api_calls, sessions

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_PATTERN.match(line.strip())
            if not match:
                continue

            dt, lvl, message = match.groups()
            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": message.strip()})
            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": message.strip()})
            elif lvl == "INFO":
                uid, action, endpoint, dur = _parse_info_message(message)
                if uid is not None and action is not None:
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                elif endpoint is not None and dur is not None:
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})

    return d_list, api_calls, sessions


def transform_metrics(
    d_list: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]],
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Transforms raw log records into error counts and endpoint latencies.

    Args:
        d_list: List of log records.
        api_calls: List of API call metrics.

    Returns:
        A tuple containing:
        - error_counts: A dictionary mapping error message to count.
        - api_latencies: A dictionary mapping endpoint to list of latencies.
    """
    error_counts: Dict[str, int] = {}
    for x in d_list:
        if x.get("t") == "ERR":
            msg = x["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    api_latencies: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        api_latencies.setdefault(ep, []).append(call["ms"])

    return error_counts, api_latencies


def load_to_database(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Loads transformed metrics into the database.

    Args:
        error_counts: Dictionary of error message to count.
        api_latencies: Dictionary of endpoint to list of latencies.
    """
    db_path = os.getenv("DB_PATH", "metrics.db")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "admin")
    db_pass = os.getenv("DB_PASS", "password123")

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
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in api_latencies.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def load_report_html(
    report_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    sessions: Dict[str, str],
) -> None:
    """Generates the HTML report.

    Args:
        report_path: Path to the output HTML file.
        error_counts: Dictionary of error message to count.
        api_latencies: Dictionary of endpoint to list of latencies.
        sessions: Dictionary of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrates the ETL pipeline."""
    log_file = os.getenv("LOG_FILE", "server.log")
    report_file = "report.html"

    # 1. Extract
    d_list, api_calls, sessions = extract_log_data(log_file)

    # 2. Transform
    error_counts, api_latencies = transform_metrics(d_list, api_calls)

    # 3. Load
    load_to_database(error_counts, api_latencies)
    load_report_html(report_file, error_counts, api_latencies, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_file_path = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
