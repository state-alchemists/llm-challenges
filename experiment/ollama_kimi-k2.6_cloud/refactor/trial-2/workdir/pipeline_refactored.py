"""ETL pipeline that parses server logs, stores metrics in SQLite, and generates an HTML report."""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


def get_config() -> Dict[str, str]:
    """Return configuration loaded from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def extract_log_entries(
    log_file: str,
) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, str]]]:
    """Extract events, active sessions, and API calls from a server log file.

    Args:
        log_file: Path to the log file to parse.

    Returns:
        A tuple of (events, sessions, api_calls).
        - events: A list of error and warning event dictionaries.
        - sessions: A dictionary mapping active user IDs to their login timestamps.
        - api_calls: A list of API call dictionaries containing endpoint and duration.
    """
    events: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, str]] = []

    error_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$")
    warn_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$")
    user_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.*)$"
    )
    api_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+)(?: took (\d+)ms)?$"
    )

    if not os.path.exists(log_file):
        return events, sessions, api_calls

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if match := error_re.match(line):
                dt, msg = match.groups()
                events.append({"d": dt, "t": "ERR", "m": msg})
            elif match := warn_re.match(line):
                dt, msg = match.groups()
                events.append({"d": dt, "t": "WARN", "m": msg})
            elif match := user_re.match(line):
                dt, uid, action = match.groups()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
                events.append({"d": dt, "t": "USR", "u": uid, "a": action})
            elif match := api_re.match(line):
                dt, endpoint, dur_str = match.groups()
                dur = int(dur_str) if dur_str else 0
                api_calls.append({"d": dt, "endpoint": endpoint, "ms": str(dur)})

    return events, sessions, api_calls


def transform_errors(events: List[Dict[str, str]]) -> Dict[str, int]:
    """Aggregate error events by message.

    Args:
        events: List of event dictionaries.

    Returns:
        A dictionary mapping error messages to occurrence counts.
    """
    error_counts: Dict[str, int] = {}
    for event in events:
        if event.get("t") == "ERR":
            msg = event["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
    return error_counts


def transform_api_latencies(api_calls: List[Dict[str, str]]) -> Dict[str, float]:
    """Compute average latency per API endpoint.

    Args:
        api_calls: List of API call dictionaries.

    Returns:
        A dictionary mapping endpoint paths to average latency in milliseconds.
    """
    endpoint_times: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        endpoint = call["endpoint"]
        ms = int(call["ms"])
        endpoint_times[endpoint].append(ms)

    latencies: Dict[str, float] = {}
    for endpoint, times in endpoint_times.items():
        latencies[endpoint] = sum(times) / len(times)
    return latencies


def load_metrics(
    db_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, float],
) -> None:
    """Load transformed metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Aggregated error message counts.
        api_latencies: Aggregated API endpoint latencies.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg in api_latencies.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, float],
    active_sessions: int,
) -> str:
    """Generate an HTML report string.

    Args:
        error_counts: Aggregated error message counts.
        api_latencies: Aggregated API endpoint latencies.
        active_sessions: Number of currently active user sessions.

    Returns:
        A complete HTML document as a string.
    """
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    html += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        html += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latencies.items():
        html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    html += "</table>\n"

    html += "<h2>Active Sessions</h2>\n"
    html += f"<p>{active_sessions} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    return html


def main() -> None:
    """Orchestrate the Extract-Transform-Load pipeline and HTML report generation."""
    config = get_config()
    db_path = config["db_path"]
    log_file = config["log_file"]
    db_host = config["db_host"]
    db_port = config["db_port"]
    db_user = config["db_user"]
    db_pass = config["db_pass"]

    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    events, sessions, api_calls = extract_log_entries(log_file)
    error_counts = transform_errors(events)
    api_latencies = transform_api_latencies(api_calls)
    load_metrics(db_path, error_counts, api_latencies)

    active_sessions = len(sessions)
    report_html = generate_report(error_counts, api_latencies, active_sessions)

    with open("report.html", "w", encoding="utf-8") as f:
        f.write(report_html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    cfg = get_config()
    log_path = cfg["log_file"]
    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
