"""
Pipeline: parse server logs, aggregate metrics, and generate an HTML report.

Usage:
    LOG_FILE=server.log DB_PATH=metrics.db python pipeline_refactored.py

Environment variables (all optional — fallback defaults shown):
    LOG_FILE  — path to the server log           (default: server.log)
    DB_PATH   — path to the SQLite database       (default: metrics.db)
    DB_HOST   — hostname (informational)          (default: localhost)
    DB_PORT   — port (informational)              (default: 5432)
    DB_USER   — username (informational)          (default: admin)
    DB_PASS   — password (informational)          (default: changeme)
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration — all from environment variables
# ---------------------------------------------------------------------------

LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "changeme")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
)
_USER_RE = re.compile(r"^User (\S+) (.+)$")
_API_RE = re.compile(r"^API (\S+) took (\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_logs(log_path: str) -> List[dict]:
    """Parse a server log file into a list of structured entries.

    Each entry dict has a ``level`` key (``"ERR"``, ``"WARN"``, ``"USR"``,
    or ``"API"``) plus level-specific fields. Unknown/informational lines
    that match no known pattern are silently skipped.

    Args:
        log_path: Path to the log file.

    Returns:
        A list of parsed log entry dicts.
    """
    entries: List[dict] = []

    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m = _LINE_RE.match(line)
            if not m:
                continue

            timestamp, level, body = m.groups()

            if level == "ERROR":
                entries.append({
                    "timestamp": timestamp,
                    "level": "ERR",
                    "message": body,
                })

            elif level == "WARN":
                entries.append({
                    "timestamp": timestamp,
                    "level": "WARN",
                    "message": body,
                })

            elif level == "INFO":
                user_m = _USER_RE.match(body)
                if user_m:
                    uid, action = user_m.groups()
                    entries.append({
                        "timestamp": timestamp,
                        "level": "USR",
                        "uid": uid,
                        "action": action,
                    })
                    continue

                api_m = _API_RE.match(body)
                if api_m:
                    endpoint, ms_str = api_m.groups()
                    entries.append({
                        "timestamp": timestamp,
                        "level": "API",
                        "endpoint": endpoint,
                        "latency_ms": int(ms_str),
                    })
                    continue

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_logs(
    entries: List[dict],
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Aggregate parsed log entries into error counts, API latencies, and
    active session count.

    Session tracking: a ``"logged in"`` action starts a session (keyed by
    user id); ``"logged out"`` ends it. The count returned is the number of
    sessions that remained active at the end of the log.

    Args:
        entries: Output of :func:`extract_logs`.

    Returns:
        A tuple ``(error_summary, api_latencies, active_sessions)``:
        - ``error_summary``:  ``{error_message: count}``
        - ``api_latencies``:  ``{endpoint: [latency_ms, ...]}``
        - ``active_sessions``: number of sessions still active.
    """
    error_summary: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in entries:
        level = entry.get("level")

        if level == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

        elif level == "API":
            ep = entry["endpoint"]
            api_latencies.setdefault(ep, []).append(entry["latency_ms"])

        elif level == "USR":
            uid = entry["uid"]
            action = entry["action"]
            if "logged in" in action:
                sessions[uid] = entry["timestamp"]
            elif "logged out" in action and uid in sessions:
                del sessions[uid]

    return error_summary, api_latencies, len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Write aggregated metrics into a SQLite database.

    Uses parameterised queries (``?`` placeholders) to prevent SQL injection.
    Creates tables if they do not already exist.

    Args:
        db_path: Path to the SQLite database file.
        error_summary:  ``{error_message: count}`` from :func:`transform_logs`.
        api_latencies:  ``{endpoint: [latency_ms, ...]}`` from :func:`transform_logs`.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in error_summary.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: int,
) -> str:
    """Build an HTML report string from aggregated data.

    The report contains three sections:
    - Error summary (unordered list of error messages and counts)
    - API latency table (endpoint, average ms)
    - Active session count

    Args:
        error_summary:   ``{error_message: count}``.
        api_latencies:   ``{endpoint: [latency_ms, ...]}``.
        active_sessions: Number of currently active user sessions.

    Returns:
        Complete HTML document as a string.
    """
    parts: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_summary.items():
        parts.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    parts.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        parts.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    parts.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Orchestrate the ETL pipeline: extract, transform, load, report.

    Reads configuration from module-level environment-variable bindings,
    parses the server log, aggregates metrics, writes results to a SQLite
    database, and produces ``report.html``.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    entries = extract_logs(LOG_FILE)
    error_summary, api_latencies, active_sessions = transform_logs(entries)
    load_to_db(DB_PATH, error_summary, api_latencies)

    html = generate_report(error_summary, api_latencies, active_sessions)
    with open("report.html", "w") as f:
        f.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Seed a sample log file if none exists (keeps the script self-contained
    # for quick smoke tests).
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
