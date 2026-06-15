"""Server log pipeline — extract, transform, and load into SQLite + HTML report.

Usage:
    PIPELINE_LOG_FILE=server.log PIPELINE_DB_PATH=metrics.db python pipeline_refactored.py

All configuration is read from environment variables (see module-level constants
for the full list and their defaults).
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Configuration — all from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches: TIMESTAMP LEVEL rest_of_line
_LOG_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)

# Matches: User <id> <action text>
_USER_PATTERN: re.Pattern[str] = re.compile(
    r"^User (?P<user_id>\S+) (?P<action>.+)$"
)

# Matches: API <endpoint> [took <duration>ms]
_API_PATTERN: re.Pattern[str] = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def _parse_info_entry(entry: dict[str, Any], payload: str) -> dict[str, Any]:
    """Augment *entry* by matching *payload* against known INFO sub-patterns."""
    if (user_match := _USER_PATTERN.match(payload)):
        entry["type"] = "user_action"
        entry["user_id"] = user_match.group("user_id")
        entry["action"] = user_match.group("action")
    elif (api_match := _API_PATTERN.match(payload)):
        entry["type"] = "api_call"
        entry["endpoint"] = api_match.group("endpoint")
        raw_dur = api_match.group("duration")
        entry["duration_ms"] = int(raw_dur) if raw_dur else 0
    else:
        entry["type"] = "info"
        entry["message"] = payload
    return entry


def extract_logs(filepath: str) -> list[dict[str, Any]]:
    """Read and parse every line in the log file.

    Returns a list of structured dicts, one per parseable line.
    Unparseable or blank lines are silently skipped.
    """
    entries: list[dict[str, Any]] = []

    if not os.path.exists(filepath):
        print(f"Log file '{filepath}' not found — no data to extract.")
        return entries

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _LOG_PATTERN.match(line)
            if not match:
                continue

            entry: dict[str, Any] = {
                "timestamp": match.group("timestamp"),
                "level": match.group("level"),
            }
            payload = match.group("message")
            level = match.group("level")

            if level == "ERROR":
                entry["type"] = "error"
                entry["message"] = payload
            elif level == "WARN":
                entry["type"] = "warn"
                entry["message"] = payload
            elif level == "INFO":
                entry = _parse_info_entry(entry, payload)

            entries.append(entry)

    print(f"Extracted {len(entries)} log entries from '{filepath}'.")
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def compute_error_summary(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.get("type") == "error":
            counts[e["message"]] += 1
    return dict(counts)


def compute_api_latency(entries: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Group API-call durations (ms) by endpoint name."""
    stats: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        if e.get("type") == "api_call":
            stats[e["endpoint"]].append(e["duration_ms"])
    return dict(stats)


def compute_active_sessions(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Replay login/logout events to determine currently active sessions.

    Returns a dict mapping *user_id* → *login_timestamp* for every user
    who has logged in but not yet logged out.
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if e.get("type") != "user_action":
            continue
        uid = e["user_id"]
        action = e["action"]
        if "logged in" in action:
            sessions[uid] = e["timestamp"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return sessions


# ---------------------------------------------------------------------------
# Load — data store
# ---------------------------------------------------------------------------


def _get_connection() -> sqlite3.Connection:
    """Create and return a connection to the metrics database.

    The host/port/user/pass config is printed for diagnostics even though
    this implementation uses SQLite (controlled via *DB_PATH*).
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    """Ensure required tables exist (idempotent)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_error_summary(
    conn: sqlite3.Connection, error_summary: dict[str, int]
) -> None:
    """Persist error counts using a parameterised insert."""
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in error_summary.items()],
    )
    conn.commit()


def load_api_latency(
    conn: sqlite3.Connection, api_latency: dict[str, list[int]]
) -> None:
    """Persist per-endpoint average latencies using a parameterised insert."""
    now = datetime.datetime.now().isoformat()
    rows = [
        (now, ep, sum(times) / len(times))
        for ep, times in api_latency.items()
    ]
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Load — report
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Minimal HTML-escaping for safe string interpolation."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_html_report(
    error_summary: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Write an HTML report covering errors, API latency, and active sessions.

    The report structure mirrors the original output so downstream consumers
    receive the same information.
    """
    parts: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in sorted(error_summary.items(), key=lambda x: -x[1]):
        parts.append(
            f"<li><b>{_escape_html(msg)}</b>: {count} occurrences</li>"
        )
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in sorted(api_latency.items()):
        avg = sum(times) / len(times)
        parts.append(
            f"<tr><td>{_escape_html(ep)}</td><td>{avg:.1f}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(parts))

    print(f"Report written to '{output_path}'.")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full extract → transform → load pipeline."""
    entries = extract_logs(LOG_FILE)
    error_summary = compute_error_summary(entries)
    api_latency = compute_api_latency(entries)
    active_sessions = compute_active_sessions(entries)

    conn = _get_connection()
    try:
        _init_db(conn)
        load_error_summary(conn, error_summary)
        load_api_latency(conn, api_latency)
    finally:
        conn.close()

    write_html_report(error_summary, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
