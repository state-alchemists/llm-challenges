"""Refactored pipeline that processes server logs and generates an HTML report.

Follows an ETL pattern:
    - Extract: Read and parse log lines with regular expressions.
    - Transform: Aggregate error frequencies, compute API latency averages,
      and track active user sessions.
    - Load: Persist aggregates to SQLite and write report.html.
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration (environment variables with sensible defaults)
# ---------------------------------------------------------------------------

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Regular expressions for robust log parsing
# ---------------------------------------------------------------------------

_LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s"
    r"(?P<level>INFO|ERROR|WARN)\s"
    r"(?P<message>.*)$"
)

_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_log_data(log_path: str) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, str]]]:
    """Parse the server log and return raw events, sessions, and API calls.

    Args:
        log_path: Path to the log file.

    Returns:
        A tuple of:
            - events: List of error / user / warning events.
            - sessions: Mapping of user_id -> last seen timestamp.
            - api_calls: List of API call records with timing.
    """
    events: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, str]] = []

    if not os.path.exists(log_path):
        return events, sessions, api_calls

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            match = _LOG_RE.match(line)
            if not match:
                continue

            level = match.group("level")
            timestamp = match.group("timestamp")
            message = match.group("message")

            if level == "ERROR":
                events.append({"d": timestamp, "t": "ERR", "m": message})

            elif level == "INFO":
                user_match = _USER_RE.match(message)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action")
                    if "logged in" in action:
                        sessions[uid] = timestamp
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    events.append({"d": timestamp, "t": "USR", "u": uid, "a": action})
                else:
                    api_match = _API_RE.match(message)
                    if api_match:
                        api_calls.append({
                            "d": timestamp,
                            "endpoint": api_match.group("endpoint"),
                            "ms": api_match.group("duration"),
                        })

            elif level == "WARN":
                events.append({"d": timestamp, "t": "WARN", "m": message})

    return events, sessions, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_metrics(
    events: List[Dict[str, str]],
    api_calls: List[Dict[str, str]],
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Aggregate raw events into error counts and per-endpoint latency lists.

    Args:
        events: Raw event list from extraction.
        api_calls: Raw API call list from extraction.

    Returns:
        A tuple of:
            - error_counts: Message -> occurrence count.
            - endpoint_stats: Endpoint -> list of latencies in ms.
    """
    error_counts: Dict[str, int] = {}
    endpoint_stats: Dict[str, List[int]] = {}

    for ev in events:
        if ev["t"] == "ERR":
            msg = ev["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for call in api_calls:
        ep = call["endpoint"]
        duration = int(call["ms"])
        endpoint_stats.setdefault(ep, []).append(duration)

    return error_counts, endpoint_stats


# ---------------------------------------------------------------------------
# Load (database + report)
# ---------------------------------------------------------------------------

def load_to_database(
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    db_path: str,
) -> None:
    """Persist aggregated metrics to a local SQLite database using parameterized queries.

    Args:
        error_counts: Aggregated error counts.
        endpoint_stats: Aggregated API latency measurements.
        db_path: Path to the SQLite database file.
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

    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, durations in endpoint_stats.items():
        avg = sum(durations) / len(durations)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> str:
    """Build the HTML report string.

    Args:
        error_counts: Aggregated error counts.
        endpoint_stats: Aggregated API latency measurements.
        active_sessions: Currently tracked user sessions.

    Returns:
        Complete HTML document as a string.
    """
    lines: List[str] = [
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

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, durations in endpoint_stats.items():
        avg = sum(durations) / len(durations)
        lines.append(
            f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def write_report(html: str, output_path: str) -> None:
    """Write the HTML report to disk.

    Args:
        html: HTML content string.
        output_path: Destination file path.
    """
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the full ETL pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    events, sessions, api_calls = extract_log_data(LOG_FILE)
    error_counts, endpoint_stats = transform_metrics(events, api_calls)
    load_to_database(error_counts, endpoint_stats, DB_PATH)
    html = generate_report(error_counts, endpoint_stats, sessions)
    write_report(html, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
