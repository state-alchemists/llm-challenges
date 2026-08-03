"""Pipeline Refactored.

Processes server logs, extracts metrics using regex, saves metrics to a database
using parameterized queries, and generates a system report.
"""

import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple


def load_config() -> Dict[str, str]:
    """Load configuration from environment variables with safe defaults.

    Returns:
        Dict[str, str]: A dictionary containing config values.
    """
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
    }


def extract_log_lines(file_path: str) -> List[str]:
    """Read raw log lines from the specified file path.

    Args:
        file_path (str): Path to the log file.

    Returns:
        List[str]: List of raw log lines.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_log_data(
    lines: List[str]
) -> Tuple[Dict[str, int], List[Dict[str, Any]], Dict[str, str]]:
    """Parse raw log lines and compute metrics.

    Uses regex to parse dates, log levels, messages, API metrics, and user sessions.

    Args:
        lines (List[str]): Raw log lines.

    Returns:
        Tuple[Dict[str, int], List[Dict[str, Any]], Dict[str, str]]:
            - errors: Dict of error messages to occurrences.
            - api_calls: List of dicts with api call metrics.
            - sessions: Dict of active user sessions (uid -> login time).
    """
    log_line_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
    )
    user_re = re.compile(r"^User\s+(\S+)\s+(.*)$")
    api_re = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    errors: Dict[str, int] = {}
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    for line in lines:
        line_match = log_line_re.match(line.strip())
        if not line_match:
            continue

        dt, lvl, message = line_match.groups()

        if lvl == "ERROR":
            err_msg = message.strip()
            errors[err_msg] = errors.get(err_msg, 0) + 1

        elif lvl == "INFO":
            # Check if User action
            user_match = user_re.match(message)
            if user_match:
                uid, action = user_match.groups()
                action = action.strip()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
            else:
                # Check if API metric
                api_match = api_re.match(message)
                if api_match:
                    endpoint, dur_str = api_match.groups()
                    dur = int(dur_str) if dur_str else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})

    return errors, api_calls, sessions


def load_data_to_db(
    db_path: str,
    errors: Dict[str, int],
    api_calls: List[Dict[str, Any]],
    db_host: str,
    db_port: str,
    db_user: str,
) -> None:
    """Save parsed metrics and errors into the database.

    Args:
        db_path (str): Path to SQLite database file.
        errors (Dict[str, int]): Dict of error messages to counts.
        api_calls (List[Dict[str, Any]]): List of parsed API calls.
        db_host (str): Database host (for logging/compatibility).
        db_port (str): Database port (for logging/compatibility).
        db_user (str): Database user (for logging/compatibility).
    """
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

        # Insert errors
        for msg, count in errors.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        # Aggregate api metrics by endpoint
        endpoint_stats: Dict[str, List[int]] = {}
        for call in api_calls:
            ep = call["endpoint"]
            endpoint_stats.setdefault(ep, []).append(call["ms"])

        # Insert api metrics
        for ep, times in endpoint_stats.items():
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    report_path: str,
    errors: Dict[str, int],
    api_calls: List[Dict[str, Any]],
    sessions: Dict[str, str],
) -> None:
    """Generate system HTML report from collected metrics.

    Args:
        report_path (str): Target HTML file path.
        errors (Dict[str, int]): Dict of error messages to counts.
        api_calls (List[Dict[str, Any]]): List of parsed API calls.
        sessions (Dict[str, str]): Dict of active sessions.
    """
    # Calculate API statistics for the report
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Orchestrate the Extract, Transform, Load (ETL) pipeline."""
    # 1. Load configuration
    config = load_config()

    db_path = config["DB_PATH"]
    log_file = config["LOG_FILE"]
    db_host = config["DB_HOST"]
    db_port = config["DB_PORT"]
    db_user = config["DB_USER"]

    # Generate fallback log file if it doesn't exist
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # 2. Extract
    lines = extract_log_lines(log_file)

    # 3. Transform
    errors, api_calls, sessions = transform_log_data(lines)

    # 4. Load
    load_data_to_db(db_path, errors, api_calls, db_host, db_port, db_user)

    # 5. Report
    generate_html_report("report.html", errors, api_calls, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
