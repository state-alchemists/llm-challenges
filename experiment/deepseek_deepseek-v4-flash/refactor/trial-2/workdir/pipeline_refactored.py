"""
Pipeline: Extract server logs, transform into metrics, load into SQLite and HTML report.

Configuration via environment variables:
    SERVER_LOG_PATH   — path to the server log file (default: server.log)
    DATABASE_PATH     — path to the SQLite database   (default: metrics.db)
"""

import datetime
import os
import re
import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE = os.getenv("SERVER_LOG_PATH", "server.log")
DB_PATH = os.getenv("DATABASE_PATH", "metrics.db")

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<body>.+)$"
)

_INFO_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_INFO_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration_ms>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

LogEvent = dict[str, Any]
ApiCall = dict[str, Any]


def parse_log_line(line: str) -> LogEvent | None:
    """Parse a single log line into a structured event dict, or None if unparseable."""
    match = _LOG_LINE_RE.match(line)
    if not match:
        return None

    timestamp: str = match.group("timestamp")
    level: str = match.group("level")
    body: str = match.group("body")

    event: LogEvent = {"timestamp": timestamp, "level": level}

    if level == "ERROR":
        event["message"] = body
    elif level == "WARN":
        event["message"] = body
    elif level == "INFO":
        user_match = _INFO_USER_RE.match(body)
        if user_match:
            event["type"] = "user_action"
            event["user_id"] = user_match.group("user_id")
            event["action"] = user_match.group("action")
        else:
            api_match = _INFO_API_RE.match(body)
            if api_match:
                event["type"] = "api_call"
                event["endpoint"] = api_match.group("endpoint")
                event["duration_ms"] = int(api_match.group("duration_ms"))

    return event


def parse_log_file(path: str) -> list[LogEvent]:
    """Read and parse every line of the log file. Skips unparseable lines."""
    if not os.path.exists(path):
        return []

    events: list[LogEvent] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = parse_log_line(line)
            if event is not None:
                events.append(event)
    return events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def aggregate_errors(events: list[LogEvent]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for ev in events:
        if ev["level"] == "ERROR":
            msg = ev["message"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def compute_latency_stats(
    events: list[LogEvent],
) -> dict[str, float]:
    """Compute average latency (ms) per API endpoint."""
    groups: dict[str, list[int]] = {}
    for ev in events:
        if ev.get("type") == "api_call":
            ep = ev["endpoint"]
            groups.setdefault(ep, []).append(ev["duration_ms"])

    averages: dict[str, float] = {}
    for ep, durations in groups.items():
        averages[ep] = sum(durations) / len(durations)
    return averages


def count_active_sessions(events: list[LogEvent]) -> int:
    """Simulate session tracking: returns count of users still logged in."""
    sessions: dict[str, str] = {}
    for ev in events:
        if ev.get("type") != "user_action":
            continue
        uid = ev["user_id"]
        action = ev["action"]
        if "logged in" in action:
            sessions[uid] = ev["timestamp"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _init_database(conn: sqlite3.Connection) -> None:
    """Create tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_to_database(
    db_path: str,
    error_summary: dict[str, int],
    latency_stats: dict[str, float],
) -> None:
    """Persist aggregated metrics into SQLite using parameterized queries."""
    conn = sqlite3.connect(db_path)
    try:
        _init_database(conn)
        now = datetime.datetime.now().isoformat()

        for msg, count in error_summary.items():
            conn.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, avg_ms in latency_stats.items():
            conn.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    error_summary: dict[str, int],
    latency_stats: dict[str, float],
    active_session_count: int,
) -> str:
    """Build an HTML report string from the aggregated metrics."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_summary.items():
        lines.append(f"    <li><b>{msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in sorted(latency_stats.items()):
        lines.append(f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines)


def write_report(path: str, html: str) -> None:
    """Write the HTML report to disk."""
    with open(path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(log_path: str, db_path: str, report_path: str = "report.html") -> None:
    """Execute the full extract → transform → load pipeline.

    Reads *log_path*, derives metrics, writes them to *db_path* (SQLite),
    and produces an HTML report at *report_path*.
    """
    events = parse_log_file(log_path)

    error_summary = aggregate_errors(events)
    latency_stats = compute_latency_stats(events)
    active_sessions = count_active_sessions(events)

    load_to_database(db_path, error_summary, latency_stats)

    html = generate_html_report(error_summary, latency_stats, active_sessions)
    write_report(report_path, html)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _ensure_sample_log(path: str) -> None:
    """Write a sample log file when none exists (dev/test helper)."""
    if os.path.exists(path):
        return
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
        "",
    ]
    with open(path, "w") as f:
        f.writelines(line + "\n" for line in lines)


def main() -> None:
    """Orchestrate pipeline startup with sample data fallback."""
    _ensure_sample_log(LOG_FILE)
    run_pipeline(LOG_FILE, DB_PATH)


if __name__ == "__main__":
    main()
