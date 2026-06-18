"""Log-processing pipeline: Extract → Transform → Load.

Reads a server log, parses events with regex, aggregates metrics,
persists results to SQLite with parameterized queries, and emits
an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration (loaded from environment)
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log line parsing
# ---------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<message>.*)$"
)

_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class ParsedEvent:
    """Represents a generic log event after extraction."""

    def __init__(self, timestamp: str, level: str, message: str) -> None:
        self.timestamp = timestamp
        self.level = level
        self.message = message


class ApiCall:
    """Represents an API latency measurement."""

    def __init__(self, timestamp: str, endpoint: str, duration_ms: int) -> None:
        self.timestamp = timestamp
        self.endpoint = endpoint
        self.duration_ms = duration_ms


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def parse_log_line(line: str) -> Tuple[ParsedEvent | None, ApiCall | None]:
    """Parse a single log line into a generic event and/or an API call.

    Args:
        line: Raw text line from the server log.

    Returns:
        A 2-tuple of (event, api_call). Either element may be ``None``
        depending on the log line contents.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None, None

    ts = match.group("timestamp")
    level = match.group("level")
    msg = match.group("message")

    event: ParsedEvent | None = None
    api_call: ApiCall | None = None

    if level in ("ERROR", "WARN"):
        event = ParsedEvent(ts, level, msg)
    elif level == "INFO":
        if msg.startswith("User "):
            um = _USER_RE.match(msg)
            if um:
                event = ParsedEvent(ts, level, msg)
        elif msg.startswith("API "):
            am = _API_RE.match(msg)
            if am:
                endpoint = am.group("endpoint")
                dur = int(am.group("duration"))
                api_call = ApiCall(ts, endpoint, dur)
                event = ParsedEvent(ts, level, msg)
        else:
            event = ParsedEvent(ts, level, msg)
    else:
        event = ParsedEvent(ts, level, msg)

    return event, api_call


def extract(log_path: str) -> Tuple[List[ParsedEvent], List[ApiCall], Dict[str, str]]:
    """Read the server log and extract events, API calls, and session state.

    Args:
        log_path: Path to the log file on disk.

    Returns:
        A 3-tuple of (events, api_calls, active_sessions).
        ``active_sessions`` maps user ID to the login timestamp.
    """
    events: List[ParsedEvent] = []
    api_calls: List[ApiCall] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_path):
        return events, api_calls, sessions

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            event, api_call = parse_log_line(line)
            if event:
                events.append(event)
                if event.level == "INFO" and event.message.startswith("User "):
                    um = _USER_RE.match(event.message)
                    if um:
                        uid = um.group("uid")
                        action = um.group("action")
                        if "logged in" in action:
                            sessions[uid] = event.timestamp
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
            if api_call:
                api_calls.append(api_call)

    return events, api_calls, sessions


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def transform(
    events: List[ParsedEvent],
    api_calls: List[ApiCall],
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Aggregate extracted data into metrics suitable for loading.

    Args:
        events: List of parsed log events.
        api_calls: List of parsed API calls.

    Returns:
        A 2-tuple of (error_counts, endpoint_stats).
        * ``error_counts`` maps error message to occurrence count.
        * ``endpoint_stats`` maps endpoint to a list of durations.
    """
    error_counts: Dict[str, int] = {}
    for ev in events:
        if ev.level == "ERROR":
            error_counts[ev.message] = error_counts.get(ev.message, 0) + 1

    endpoint_stats: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        endpoint_stats[call.endpoint].append(call.duration_ms)

    return error_counts, endpoint_stats


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_db(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message → occurrence count.
        endpoint_stats: Mapping of endpoint → list of latency measurements.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
        """
    )

    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, round(avg, 2)),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions: int,
) -> str:
    """Build the HTML report string from aggregated metrics.

    Args:
        error_counts: Mapping of error message → occurrence count.
        endpoint_stats: Mapping of endpoint → list of latency measurements.
        active_sessions: Number of currently active user sessions.

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
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>", "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def write_report(report_path: str, html: str) -> None:
    """Write the HTML report to disk.

    Args:
        report_path: Destination path for the HTML file.
        html: Complete HTML content.
    """
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def ensure_sample_log(log_path: str) -> None:
    """Create a sample log file if none exists so the demo can run."""
    if os.path.exists(log_path):
        return
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    ensure_sample_log(LOG_FILE)

    # Extract
    events, api_calls, sessions = extract(LOG_FILE)

    # Transform
    error_counts, endpoint_stats = transform(events, api_calls)

    # Load
    load_db(DB_PATH, error_counts, endpoint_stats)
    html = generate_report(error_counts, endpoint_stats, len(sessions))
    write_report("report.html", html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
