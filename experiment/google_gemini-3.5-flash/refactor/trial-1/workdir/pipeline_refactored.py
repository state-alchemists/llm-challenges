"""Pipeline script to process server logs and generate a report."""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration using environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular expressions for parsing log lines
LOG_LINE_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
)
USER_ACTION_PATTERN: re.Pattern = re.compile(r"^User (\S+)\s+(.*)$")
API_CALL_PATTERN: re.Pattern = re.compile(r"^API (\S+)(?: took (\d+)ms)?")


def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """Extracts raw events from the log file using regular expressions.

    Args:
        log_file_path: The file path to the log file.

    Returns:
        A list of parsed log event dictionaries.
    """
    events: List[Dict[str, Any]] = []
    if not os.path.exists(log_file_path):
        return events

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = LOG_LINE_PATTERN.match(line)
            if not match:
                continue

            dt, level, message = match.groups()

            if level == "ERROR":
                events.append({
                    "type": "ERROR",
                    "timestamp": dt,
                    "message": message,
                })
            elif level == "INFO":
                user_match = USER_ACTION_PATTERN.match(message)
                if user_match:
                    uid, action = user_match.groups()
                    events.append({
                        "type": "USER",
                        "timestamp": dt,
                        "uid": uid,
                        "action": action,
                    })
                else:
                    api_match = API_CALL_PATTERN.match(message)
                    if api_match:
                        endpoint, dur_str = api_match.groups()
                        duration = int(dur_str) if dur_str else 0
                        events.append({
                            "type": "API",
                            "timestamp": dt,
                            "endpoint": endpoint,
                            "duration_ms": duration,
                        })
            elif level == "WARN":
                events.append({
                    "type": "WARN",
                    "timestamp": dt,
                    "message": message,
                })

    return events


def transform_log_data(
    events: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Transforms raw log events into aggregate metrics.

    Calculates error frequencies, API endpoint response times, and
    active user session counts.

    Args:
        events: A list of parsed log events.

    Returns:
        A tuple of:
            - A dictionary mapping error messages to occurrence counts.
            - A dictionary mapping endpoints to lists of latency values.
            - The count of active user sessions at the end of the log.
    """
    error_summary: Dict[str, int] = {}
    api_metrics: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for event in events:
        evt_type = event["type"]
        if evt_type == "ERROR":
            msg = event["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif evt_type == "API":
            endpoint = event["endpoint"]
            duration = event["duration_ms"]
            api_metrics.setdefault(endpoint, []).append(duration)
        elif evt_type == "USER":
            uid = event["uid"]
            action = event["action"]
            dt = event["timestamp"]
            if "logged in" in action:
                active_sessions[uid] = dt
            elif "logged out" in action:
                active_sessions.pop(uid, None)

    return error_summary, api_metrics, len(active_sessions)


def load_metrics_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    api_metrics: Dict[str, List[int]],
) -> None:
    """Loads transformed metrics to the database using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        error_summary: Frequencies of error messages.
        api_metrics: Response times grouped by endpoint.
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

        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in api_metrics.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_summary: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_session_count: int,
) -> None:
    """Generates the HTML summary report.

    Args:
        report_path: Path to save the HTML report.
        error_summary: Frequency count of errors.
        api_metrics: API latencies per endpoint.
        active_session_count: Total active sessions at log completion.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution function to run the ETL pipeline."""
    # Ensure raw log data is extracted
    events = extract_log_data(LOG_FILE)

    # Transform events into aggregates
    error_summary, api_metrics, active_session_count = transform_log_data(events)

    # Load aggregated data into the database
    load_metrics_to_db(DB_PATH, error_summary, api_metrics)

    # Load/generate HTML report
    generate_report("report.html", error_summary, api_metrics, active_session_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_out:
            f_out.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_out.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_out.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_out.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
