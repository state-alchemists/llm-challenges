"""Server log processing pipeline: extract, transform, and load server metrics.

Config (all via environment variables):
    PIPELINE_DB_PATH     — SQLite database path (default: metrics.db)
    PIPELINE_LOG_FILE    — path to the server log (default: server.log)
    PIPELINE_REPORT_FILE — path for the HTML report (default: report.html)

Log format expected per line:
    YYYY-MM-DD HH:MM:SS LEVEL message...
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("PIPELINE_REPORT_FILE", "report.html")

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\S+) "
    r"(?P<message>.+)$"
)

_USER_PATTERN = re.compile(r"^User\s+(\d+)\s+(.+)$")

_API_PATTERN = re.compile(r"^API\s+(\S+)\s+took\s+(\d+)ms$")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

LogEntry = dict[str, Any]
"""Parsed log entry: {'dt': str, 'level': str, 'message': str,
   plus optional keys 'user', 'action', 'endpoint', 'ms' depending on type."""

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single server log line into a structured dict, or None if unparseable."""
    m = _LOG_PATTERN.match(line.strip())
    if not m:
        return None
    entry: LogEntry = {
        "dt": m.group("timestamp"),
        "level": m.group("level"),
        "message": m.group("message"),
    }
    return entry


def extract_logs(path: str) -> list[LogEntry]:
    """Read and parse every line of the log file at *path*.

    Returns a list of parsed LogEntry dicts; lines that don't match the
    expected format are silently skipped.
    """
    entries: list[LogEntry] = []
    if not os.path.exists(path):
        return entries
    with open(path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def classify_entries(
    entries: list[LogEntry],
) -> tuple[list[LogEntry], dict[str, str], list[LogEntry]]:
    """Classify raw log entries into three collections.

    Returns:
        (error_entries, active_sessions, api_entries)

    *error_entries* — all ERROR-level entries.
    *active_sessions* — a {user_id: login_timestamp} map reflecting the
        state after all log entries have been replayed.
    *api_entries* — all INFO-level API-call entries with their endpoint
        and duration resolved, or an empty list.
    """
    error_entries: list[LogEntry] = []
    api_entries: list[LogEntry] = []
    active_sessions: dict[str, str] = {}

    for entry in entries:
        level = entry["level"]
        message = entry["message"]

        if level == "ERROR":
            error_entries.append(entry)

        elif level == "INFO":
            # --- User session events ---
            user_m = _USER_PATTERN.match(message)
            if user_m:
                uid, action = user_m.group(1), user_m.group(2)
                entry["user"] = uid
                entry["action"] = action
                if "logged in" in action:
                    active_sessions[uid] = entry["dt"]
                elif "logged out" in action and uid in active_sessions:
                    del active_sessions[uid]

            # --- API call events ---
            api_m = _API_PATTERN.match(message)
            if api_m:
                endpoint = api_m.group(1)
                ms = int(api_m.group(2))
                entry["endpoint"] = endpoint
                entry["ms"] = ms
                api_entries.append(entry)

    return error_entries, active_sessions, api_entries


def aggregate_errors(error_entries: list[LogEntry]) -> dict[str, int]:
    """Group identical error messages and count occurrences.

    Returns {message_text: count}.
    """
    counts: dict[str, int] = {}
    for entry in error_entries:
        msg = entry["message"]
        counts[msg] = counts.get(msg, 0) + 1
    return counts


def compute_api_latency(
    api_entries: list[LogEntry],
) -> dict[str, float]:
    """Compute average latency in ms per API endpoint.

    Returns {endpoint: average_ms}.
    """
    times_by_endpoint: dict[str, list[int]] = defaultdict(list)
    for entry in api_entries:
        times_by_endpoint[entry["endpoint"]].append(entry["ms"])

    averages: dict[str, float] = {}
    for endpoint, times in times_by_endpoint.items():
        averages[endpoint] = sum(times) / len(times)
    return averages


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def init_db(path: str) -> sqlite3.Connection:
    """Open the SQLite database at *path* and ensure required tables exist."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def insert_error_summary(
    conn: sqlite3.Connection,
    now: str,
    counts: dict[str, int],
) -> None:
    """Insert aggregated error counts into the *errors* table.

    Uses parameterised queries to avoid SQL injection.
    """
    for msg, count in counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )


def insert_api_metrics(
    conn: sqlite3.Connection,
    now: str,
    averages: dict[str, float],
) -> None:
    """Insert per-endpoint average latencies into the *api_metrics* table.

    Uses parameterised queries to avoid SQL injection.
    """
    for endpoint, avg_ms in averages.items():
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )


def generate_report(
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    session_count: int,
) -> str:
    """Build the HTML report string.

    Sections: error summary (bullet list), API latency (table), active sessions.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append('<h2>API Latency</h2>')
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg_ms in sorted(api_averages.items()):
        lines.append(f"<tr><td>{ep}</td><td>{round(avg_ms, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def write_report(html: str, path: str) -> None:
    """Write the HTML report string to *path*."""
    with open(path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full Extract → Transform → Load pipeline.

    1. Read and parse the server log
    2. Classify entries, aggregate errors, compute API latency
    3. Write results to SQLite and generate the HTML report
    """
    # --- Extract ---
    entries = extract_logs(LOG_FILE)

    # --- Transform ---
    error_entries, active_sessions, api_entries = classify_entries(entries)
    error_counts = aggregate_errors(error_entries)
    api_averages = compute_api_latency(api_entries)

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    # --- Load (database) ---
    conn = init_db(DB_PATH)
    try:
        insert_error_summary(conn, now, error_counts)
        insert_api_metrics(conn, now, api_averages)
        conn.commit()
    finally:
        conn.close()

    # --- Load (report) ---
    html = generate_report(
        error_counts=error_counts,
        api_averages=api_averages,
        session_count=len(active_sessions),
    )
    write_report(html, REPORT_FILE)

    print(f"Pipeline finished at {now}")


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
