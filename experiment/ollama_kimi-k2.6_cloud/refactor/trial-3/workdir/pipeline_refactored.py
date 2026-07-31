"""Refactored log processing pipeline.

Reads server logs, aggregates error and API-latency metrics, persists them to
SQLite, and emits an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration (loaded from environment variables)
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log line parsing
# ---------------------------------------------------------------------------
_LOG_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+(?P<rest>.+)$"
)

_USER_RE = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$"
)


def _parse_timestamp(date_str: str, time_str: str) -> str:
    """Combine date and time strings into a single timestamp."""
    return f"{date_str} {time_str}"


def extract_logs(log_path: str) -> Tuple[List[dict], Dict[str, str], List[dict]]:
    """Parse the server log file and return raw records.

    Returns:
        A tuple of (events, sessions, api_calls) where:
        - events: list of error/warning/user event dicts
        - sessions: mapping of user_id -> login_timestamp
        - api_calls: list of API call dicts with timing info
    """
    events: List[dict] = []
    sessions: Dict[str, str] = {}
    api_calls: List[dict] = []

    if not os.path.exists(log_path):
        return events, sessions, api_calls

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _LOG_TIMESTAMP_RE.match(line)
            if not match:
                continue

            date_str = match.group("date")
            time_str = match.group("time")
            level = match.group("level")
            rest = match.group("rest")
            timestamp = _parse_timestamp(date_str, time_str)

            if level == "ERROR":
                events.append({"d": timestamp, "t": "ERR", "m": rest})

            elif level == "WARN":
                events.append({"d": timestamp, "t": "WARN", "m": rest})

            elif level == "INFO":
                if rest.startswith("User "):
                    user_match = _USER_RE.match(rest)
                    if user_match:
                        uid = user_match.group("uid")
                        action = user_match.group("action")
                        if "logged in" in action:
                            sessions[uid] = timestamp
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                        events.append(
                            {"d": timestamp, "t": "USR", "u": uid, "a": action}
                        )
                elif rest.startswith("API "):
                    api_match = _API_RE.match(rest)
                    if api_match:
                        endpoint = api_match.group("endpoint")
                        duration = int(api_match.group("duration"))
                        api_calls.append(
                            {"d": timestamp, "endpoint": endpoint, "ms": duration}
                        )

    return events, sessions, api_calls


def transform_data(
    events: List[dict], api_calls: List[dict]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Aggregate raw events into summary statistics.

    Returns:
        A tuple of (error_counts, endpoint_latencies) where:
        - error_counts: mapping of error message -> occurrence count
        - endpoint_latencies: mapping of endpoint -> list of durations in ms
    """
    error_counts: Dict[str, int] = {}
    for event in events:
        if event["t"] == "ERR":
            msg = event["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_latencies: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        endpoint_latencies[call["endpoint"]].append(call["ms"])

    return dict(error_counts), dict(endpoint_latencies)


def load_to_db(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message -> count.
        endpoint_latencies: Mapping of endpoint -> list of durations in ms.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())
    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Generate an HTML report from aggregated data.

    Args:
        error_counts: Mapping of error message -> occurrence count.
        endpoint_latencies: Mapping of endpoint -> list of durations in ms.
        active_sessions: Number of currently active user sessions.
        output_path: Destination path for the HTML report.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>"
        )
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>",
                  "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])

    for endpoint, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def main() -> None:
    """Orchestrate the Extract -> Transform -> Load pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    events, sessions, api_calls = extract_logs(LOG_FILE)
    error_counts, endpoint_latencies = transform_data(events, api_calls)
    load_to_db(DB_PATH, error_counts, endpoint_latencies)
    generate_report(error_counts, endpoint_latencies, len(sessions))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
