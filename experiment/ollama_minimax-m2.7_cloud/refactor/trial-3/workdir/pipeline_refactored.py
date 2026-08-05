"""
Log processing pipeline that extracts server logs, transforms the data,
and loads error summaries + API latency metrics into an HTML report.

Requires environment variables:
  DB_PATH      - Path to SQLite database (default: metrics.db)
  LOG_FILE     - Path to server log file (default: server.log)
  DB_HOST      - Database host (default: localhost)
  DB_PORT      - Database port (default: 5432)
  DB_USER      - Database user (default: admin)
  DB_PASS      - Database password (default: password123)
"""

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# --- Config from environment ---

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")

# --- Typed data structures ---

LogEntry = TypedDict("LogEntry", {"dt": str, "t": str, "m": str})
UserEntry = TypedDict("UserEntry", {"dt": str, "t": str, "u": str, "a": str})
ApiEntry = TypedDict("ApiEntry", {"dt": str, "endpoint": str, "ms": int})
ParsedLog = tuple[list[LogEntry], list[UserEntry], list[ApiEntry]]


# --- Regex patterns for log parsing ---

_RE_ERROR = re.compile(r"^(\S+ \S+) ERROR (.+)$")
_RE_INFO_USER = re.compile(r"^(\S+ \S+) INFO User (\S+) (.+)$")
_RE_INFO_API = re.compile(r"^(\S+ \S+) INFO API (\S+) took (\d+)ms$")
_RE_WARN = re.compile(r"^(\S+ \S+) WARN (.+)$")


# === EXTRACT ===

def read_log_file(path: str) -> list[str]:
    """Read and return all lines from the log file."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        return fh.readlines()


def parse_log_line(line: str) -> tuple[LogEntry | None, UserEntry | None, ApiEntry | None]:
    """
    Parse a single log line using regex.
    Returns (error_entry, user_entry, api_entry) — two will be None.
    """
    line = line.strip()
    if not line:
        return None, None, None

    if m := _RE_ERROR.match(line):
        return {"dt": m.group(1), "t": "ERR", "m": m.group(2)}, None, None

    if m := _RE_INFO_USER.match(line):
        uid = m.group(2)
        action = m.group(3)
        user_entry: UserEntry = {"dt": m.group(1), "t": "USR", "u": uid, "a": action}
        return None, user_entry, None

    if m := _RE_INFO_API.match(line):
        return None, None, {"dt": m.group(1), "endpoint": m.group(2), "ms": int(m.group(3))}

    if m := _RE_WARN.match(line):
        return {"dt": m.group(1), "t": "WARN", "m": m.group(2)}, None, None

    return None, None, None


def extract(path: str) -> ParsedLog:
    """
    Read the log file and extract structured records.
    Returns (error_entries, user_entries, api_calls).
    """
    errors: list[LogEntry] = []
    users: list[UserEntry] = []
    api_calls: list[ApiEntry] = []

    for line in read_log_file(path):
        err, usr, api = parse_log_line(line)
        if err is not None:
            errors.append(err)
        if usr is not None:
            users.append(usr)
        if api is not None:
            api_calls.append(api)

    return errors, users, api_calls


# === TRANSFORM ===

def build_error_counts(errors: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for e in errors:
        counts[e["m"]] = counts.get(e["m"], 0) + 1
    return counts


def compute_api_latency(api_calls: list[ApiEntry]) -> dict[str, float]:
    """
    Compute average latency per endpoint.
    Returns {endpoint: avg_ms}.
    """
    buckets: dict[str, list[int]] = {}
    for call in api_calls:
        buckets.setdefault(call["endpoint"], []).append(call["ms"])
    return {ep: sum(times) / len(times) for ep, times in buckets.items()}


def track_active_sessions(user_entries: list[UserEntry]) -> int:
    """
    Walk user events in order and count currently-active sessions.
    A session starts on 'logged in' and ends on 'logged out'.
    """
    sessions: set[str] = set()
    for entry in user_entries:
        uid = entry["u"]
        action = entry["a"]
        if "logged in" in action:
            sessions.add(uid)
        elif "logged out" in action:
            sessions.discard(uid)
    return len(sessions)


def transform(errors: list[LogEntry], users: list[UserEntry], api_calls: list[ApiEntry]) -> tuple[dict[str, int], dict[str, float], int]:
    """
    Transform raw log entries into analysis-ready summaries.
    Returns (error_counts, api_latency, active_session_count).
    """
    error_counts = build_error_counts(errors)
    api_latency = compute_api_latency(api_calls)
    active_sessions = track_active_sessions(users)
    return error_counts, api_latency, active_sessions


# === LOAD ===

def init_db(db_path: str) -> sqlite3.Connection:
    """Create DB connection and ensure schema exists."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def load(db_path: str, error_counts: dict[str, int], api_latency: dict[str, float]) -> None:
    """
    Write error counts and API latency summaries to the database
    using parameterized queries.
    """
    conn = init_db(db_path)
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: int,
    output_path: str,
) -> None:
    """Render the final HTML report to disk."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, avg_ms in api_latency.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# === PIPELINE ===

def run_pipeline() -> None:
    """Execute the full ETL pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    errors, users, api_calls = extract(LOG_FILE)

    # Transform
    error_counts, api_latency, active_sessions = transform(errors, users, api_calls)

    # Load
    load(DB_PATH, error_counts, api_latency)
    generate_html_report(error_counts, api_latency, active_sessions, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


# === BOOTSTRAP ===

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
