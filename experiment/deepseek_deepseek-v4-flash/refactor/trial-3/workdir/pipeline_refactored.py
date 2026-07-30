"""Process server logs and generate a system report.

Extracts structured data from log files using regex, transforms raw
events into aggregates, and loads results into SQLite + an HTML report.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Configuration — all from environment variables
# ---------------------------------------------------------------------------

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Log line patterns
# ---------------------------------------------------------------------------

# Full line: TIMESTAMP LEVEL rest
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.*)$"
)

# INFO sub-types
_USER_EVENT_RE = re.compile(r"^User (\d+) (.+)$")
_API_CALL_RE = re.compile(r"^API (/\S+) took (\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_logs(
    filepath: str,
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    """Parse a server log file and return structured event data.

    Returns a tuple of:
        events      — all parsed log lines (ERROR, USR, WARN) as dicts
        sessions    — current active sessions {user_id: login_timestamp}
        api_calls   — API latency observations [{endpoint, ms, timestamp}]
    """
    events: list[dict[str, Any]] = []
    sessions: dict[str, str] = {}
    api_calls: list[dict[str, Any]] = []

    if not os.path.exists(filepath):
        return events, sessions, api_calls

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m = _LOG_LINE_RE.match(line)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                events.append({
                    "d": timestamp,
                    "t": "ERR",
                    "m": rest,
                })

            elif level == "WARN":
                events.append({
                    "d": timestamp,
                    "t": "WARN",
                    "m": rest,
                })

            elif level == "INFO":
                user_m = _USER_EVENT_RE.match(rest)
                if user_m:
                    uid = user_m.group(1)
                    action = user_m.group(2)
                    if "logged in" in action:
                        sessions[uid] = timestamp
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid, None)
                    events.append({
                        "d": timestamp,
                        "t": "USR",
                        "u": uid,
                        "a": action,
                    })
                    continue

                api_m = _API_CALL_RE.match(rest)
                if api_m:
                    endpoint = api_m.group(1)
                    duration = int(api_m.group(2))
                    api_calls.append({
                        "d": timestamp,
                        "endpoint": endpoint,
                        "ms": duration,
                    })
                    continue

    return events, sessions, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def _aggregate_errors(events: list[dict[str, Any]]) -> dict[str, int]:
    """Count ERROR occurrences grouped by message."""
    counts: dict[str, int] = {}
    for ev in events:
        if ev["t"] == "ERR":
            msg = ev["m"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def _aggregate_api_latency(
    api_calls: list[dict[str, Any]],
) -> dict[str, list[int]]:
    """Group API latency observations by endpoint."""
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        stats.setdefault(ep, []).append(call["ms"])
    return stats


def transform_data(
    events: list[dict[str, Any]],
    api_calls: list[dict[str, Any]],
    sessions: dict[str, str],
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """Aggregate raw log data into report-ready statistics.

    Returns:
        (error_counts, api_latency_map, active_session_count)
    """
    error_counts = _aggregate_errors(events)
    api_latency_map = _aggregate_api_latency(api_calls)
    active_session_count = len(sessions)
    return error_counts, api_latency_map, active_session_count


# ---------------------------------------------------------------------------
# Load — SQLite
# ---------------------------------------------------------------------------

def _init_db(db_path: str) -> sqlite3.Connection:
    """Open or create the metrics DB and ensure tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def _insert_error_summaries(
    cursor: sqlite3.Cursor,
    error_counts: dict[str, int],
) -> None:
    """Persist error counts with parameterized queries (no SQL injection)."""
    now = str(datetime.datetime.now())
    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )


def _insert_api_metrics(
    cursor: sqlite3.Cursor,
    api_latency_map: dict[str, list[int]],
) -> None:
    """Persist API latency averages with parameterized queries."""
    now = str(datetime.datetime.now())
    for endpoint, times in api_latency_map.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )


def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency_map: dict[str, list[int]],
) -> None:
    """Insert aggregated metrics into SQLite."""
    conn = _init_db(db_path)
    try:
        cursor = conn.cursor()
        _insert_error_summaries(cursor, error_counts)
        _insert_api_metrics(cursor, api_latency_map)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Load — HTML report
# ---------------------------------------------------------------------------

def _render_error_summary(error_counts: dict[str, int]) -> str:
    """Generate the error summary HTML section."""
    lines: list[str] = []
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_counts.items():
        safe_msg = html.escape(err_msg)
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def _render_api_latency(api_latency_map: dict[str, list[int]]) -> str:
    """Generate the API latency table HTML section."""
    lines: list[str] = []
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency_map.items():
        avg = sum(times) / len(times)
        safe_ep = html.escape(endpoint)
        lines.append(f"<tr><td>{safe_ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _render_active_sessions(count: int) -> str:
    """Generate the active sessions count HTML section."""
    return (
        f"<h2>Active Sessions</h2>\n"
        f"<p>{count} user(s) currently active</p>"
    )


def generate_html(
    error_counts: dict[str, int],
    api_latency_map: dict[str, list[int]],
    active_session_count: int,
) -> str:
    """Produce a complete HTML report string."""
    sections = [
        _render_error_summary(error_counts),
        _render_api_latency(api_latency_map),
        _render_active_sessions(active_session_count),
    ]
    return (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        f"{chr(10).join(sections)}\n"
        "</body>\n"
        "</html>"
    )


def write_html_report(
    output_path: str,
    html_content: str,
) -> None:
    """Write the report HTML to disk."""
    with open(output_path, "w") as f:
        f.write(html_content)


# ---------------------------------------------------------------------------
# Convenience: sample log data
# ---------------------------------------------------------------------------

_SEED_LOG_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


def _ensure_log_file(filepath: str) -> None:
    """Create a sample log file if none exists."""
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write("\n".join(_SEED_LOG_LINES) + "\n")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline.

    1. Extract: parse the server log into structured events.
    2. Transform: aggregate errors, API latency, and count active sessions.
    3. Load: persist metrics to SQLite and generate report.html.
    """
    _ensure_log_file(LOG_FILE)

    # Extract
    events, sessions, api_calls = extract_logs(LOG_FILE)

    print(
        f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} "
        f"(DB: {DB_PATH})..."
    )

    # Transform
    error_counts, api_latency_map, active_count = transform_data(
        events, api_calls, sessions,
    )

    # Load — DB
    load_to_db(DB_PATH, error_counts, api_latency_map)

    # Load — HTML
    html_content = generate_html(error_counts, api_latency_map, active_count)
    write_html_report("report.html", html_content)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_pipeline()
