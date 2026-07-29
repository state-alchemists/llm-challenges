"""
Server log processing pipeline.

Extracts events from server logs, aggregates metrics, and produces an HTML report.
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration — loaded from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Regex patterns for log line parsing
# ---------------------------------------------------------------------------

_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<body>.*)$"
)

_RE_USER_ACTION = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")
_RE_API_CALL = re.compile(r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$")


# ---------------------------------------------------------------------------
# EXTRACT — parse log file into structured records
# ---------------------------------------------------------------------------

def extract_log_events(log_path: str) -> Tuple[List[dict], List[dict], Dict[str, str]]:
    """
    Parse the log file and extract error, API call, and user session events.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple of (errors, api_calls, sessions) where:
        - errors: list of {"dt": timestamp, "msg": message} dicts
        - api_calls: list of {"d": timestamp, "endpoint": str, "ms": int} dicts
        - sessions: dict mapping user ID -> login timestamp
    """
    errors: List[dict] = []
    api_calls: List[dict] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_path):
        return errors, api_calls, sessions

    with open(log_path, "r") as f:
        for line in f:
            match = _RE_LOG_LINE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            body = match.group("body")

            if level == "ERROR":
                errors.append({"dt": timestamp, "msg": body.strip()})

            elif level == "INFO" and body.startswith("User "):
                user_match = _RE_USER_ACTION.match(body)
                if not user_match:
                    continue
                uid = user_match.group("uid")
                action = user_match.group("action")

                if "logged in" in action:
                    sessions[uid] = timestamp
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]

            elif level == "INFO" and body.startswith("API "):
                api_match = _RE_API_CALL.match(body)
                if api_match:
                    api_calls.append({
                        "d": timestamp,
                        "endpoint": api_match.group("endpoint"),
                        "ms": int(api_match.group("ms")),
                    })

    return errors, api_calls, sessions


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate extracted data
# ---------------------------------------------------------------------------

def transform_errors(errors: List[dict]) -> Dict[str, int]:
    """
    Count occurrences of each distinct error message.

    Args:
        errors: List of error records from the log.

    Returns:
        Dict mapping error message -> occurrence count.
    """
    counts: Dict[str, int] = {}
    for err in errors:
        counts[err["msg"]] = counts.get(err["msg"], 0) + 1
    return counts


def transform_api_latency(api_calls: List[dict]) -> Dict[str, float]:
    """
    Compute average latency per API endpoint.

    Args:
        api_calls: List of API call records from the log.

    Returns:
        Dict mapping endpoint -> average latency in ms.
    """
    endpoint_times: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_times.setdefault(call["endpoint"], []).append(call["ms"])

    return {
        ep: sum(times) / len(times)
        for ep, times in endpoint_times.items()
    }


# ---------------------------------------------------------------------------
# LOAD — write to database and generate HTML report
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    errors: Dict[str, int],
    api_latency: Dict[str, float],
) -> None:
    """
    Persist error counts and API latency metrics to the SQLite database.
    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        errors: Error message -> count dict.
        api_latency: Endpoint -> average ms dict.
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

    for msg, count in errors.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    output_path: str,
    errors: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions: int,
) -> None:
    """
    Render the aggregated metrics as an HTML report.

    Args:
        output_path: Destination file path for the HTML report.
        errors: Error message -> count dict.
        api_latency: Endpoint -> average ms dict.
        active_sessions: Number of currently active user sessions.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in errors.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, avg_ms in api_latency.items():
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract log events, transform into
    metrics, load into the database, and produce the HTML report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    errors, api_calls, sessions = extract_log_events(LOG_FILE)

    error_counts = transform_errors(errors)
    api_latency = transform_api_latency(api_calls)

    load_to_database(DB_PATH, error_counts, api_latency)
    generate_html_report("report.html", error_counts, api_latency, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
