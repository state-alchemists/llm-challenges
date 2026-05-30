"""
Log parsing and reporting pipeline.

Processes server log files to collect error, API latency, and user session statistics.
Inserts processed metrics into a database, and generates an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from pathlib import Path

# --- Environment Configurations ---
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# --- Regular Expression Patterns ---
# Parsed groups: 1=Timestamp, 2=Severity, 3=Message
LOG_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)

# Parsed groups: 1=User ID, 2=Action
USER_PATTERN: re.Pattern[str] = re.compile(r"^User\s+(\S+)\s+(.*)$")

# Parsed groups: 1=Endpoint, 2=Duration (ms)
API_PATTERN: re.Pattern[str] = re.compile(r"^API\s+(\S+)\s+took\s+(\d+)ms")


def extract_log_lines(file_path: str) -> list[str]:
    """
    Read the contents of the specified log file and return all lines.

    Args:
        file_path: Path to the log file.

    Returns:
        List of log line strings. If the file does not exist, returns an empty list.
    """
    path = Path(file_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return f.readlines()


def transform_logs(
    lines: list[str],
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, str]]:
    """
    Process raw log lines to extract error counts, API latency stats, and user sessions.

    Args:
        lines: Raw log lines to process.

    Returns:
        A tuple of three dictionaries:
        - error_counts: dict mapping error message to occurrence count
        - api_metrics: dict mapping API endpoint to list of response times (ms)
        - sessions: dict mapping user ID to login timestamp
    """
    error_counts: dict[str, int] = {}
    api_metrics: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for line in lines:
        line = line.strip()
        match = LOG_LINE_PATTERN.match(line)
        if not match:
            continue

        dt, lvl, msg = match.groups()

        if lvl == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif lvl == "INFO":
            # Match user session log lines
            user_match = USER_PATTERN.match(msg)
            if user_match:
                uid, action = user_match.groups()
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)

            # Match API performance log lines
            api_match = API_PATTERN.match(msg)
            if api_match:
                endpoint, dur_str = api_match.groups()
                dur = int(dur_str) if dur_str else 0
                api_metrics.setdefault(endpoint, []).append(dur)

    return error_counts, api_metrics, sessions


def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
) -> None:
    """
    Insert the aggregated log metrics into the SQLite database.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Dict of error messages and their occurrence counts.
        api_metrics: Dict of endpoints and lists of latency values.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    now_str = str(datetime.datetime.now())

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in api_metrics.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )

        conn.commit()


def load_report(
    report_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    sessions: dict[str, str],
) -> None:
    """
    Generate an HTML system report summarizing errors, latency, and session counts.

    Args:
        report_path: Destination path for the generated HTML report.
        error_counts: Dict of error messages and their occurrence counts.
        api_metrics: Dict of endpoints and lists of latency values.
        sessions: Dict of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    path = Path(report_path)
    path.write_text(out, encoding="utf-8")


def proc_data() -> None:
    """
    Execute the entire log processing, database insertion, and reporting pipeline.
    """
    # 1. Extract
    lines = extract_log_lines(LOG_FILE)

    # 2. Transform
    error_counts, api_metrics, sessions = transform_logs(lines)

    # 3. Load
    load_to_database(DB_PATH, error_counts, api_metrics)
    load_report("report.html", error_counts, api_metrics, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        log_path.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    proc_data()
