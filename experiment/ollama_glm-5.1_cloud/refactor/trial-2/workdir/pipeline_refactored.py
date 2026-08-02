"""Refactored server-log pipeline: Extract → Transform → Load.

Reads server logs, computes error summaries, API latency stats, and active
session counts, then stores results in SQLite and writes an HTML report.
"""

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Configuration — all values come from environment variables.
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for structured log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<message>.*)$"
)

_USER_ACTION_RE = re.compile(
    r"User\s+(?P<user_id>\S+)\s+(?P<action>.*)$"
)

_API_CALL_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration_ms>\d+)ms"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A structured log line."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A login / logout event extracted from an INFO log line."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API latency measurement extracted from an INFO log line."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedLog:
    """Aggregate of all data extracted from the log file."""
    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract — read raw log lines and parse them into structured data
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Read the log file and parse every line into structured records.

    Uses regex to robustly handle variable-width fields instead of
    fragile ``str.split()`` calls.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ``ParsedLog`` containing all categorised entries.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        return parsed

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            message = match.group("message")

            if level == "ERROR":
                parsed.errors.append(
                    LogEntry(timestamp=timestamp, level=level, message=message)
                )
            elif level == "WARN":
                parsed.warnings.append(
                    LogEntry(timestamp=timestamp, level=level, message=message)
                )
            elif level == "INFO":
                # Try parsing as a user action
                user_match = _USER_ACTION_RE.search(message)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action").strip(),
                        )
                    )
                    continue

                # Try parsing as an API call
                api_match = _API_CALL_RE.search(message)
                if api_match:
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration_ms")),
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform — compute aggregates from parsed data
# ---------------------------------------------------------------------------


def transform(payload: ParsedLog) -> Tuple[Dict[str, int], Dict[str, Tuple[float, int]], int]:
    """Compute error counts, API latency averages, and active session count.

    Args:
        payload: The ``ParsedLog`` produced by :func:`extract`.

    Returns:
        A tuple of:
          - error_counts: mapping of error message → occurrence count
          - latency_stats: mapping of endpoint → (avg_ms, sample_count)
          - active_sessions: number of users still logged in
    """
    # Error summary
    error_counts: Dict[str, int] = {}
    for entry in payload.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # API latency averages
    latency_buckets: Dict[str, List[int]] = {}
    for call in payload.api_calls:
        latency_buckets.setdefault(call.endpoint, []).append(call.duration_ms)

    latency_stats: Dict[str, Tuple[float, int]] = {}
    for endpoint, durations in latency_buckets.items():
        avg = sum(durations) / len(durations)
        latency_stats[endpoint] = (avg, len(durations))

    # Active sessions — users who logged in without a matching logout
    sessions: Dict[str, str] = {}
    for event in payload.user_events:
        if event.action == "logged in":
            sessions[event.user_id] = event.timestamp
        elif event.action == "logged out" and event.user_id in sessions:
            sessions.pop(event.user_id)

    return error_counts, latency_stats, len(sessions)


# ---------------------------------------------------------------------------
# Load — persist to SQLite and write HTML report
# ---------------------------------------------------------------------------


def load(
    db_path: str,
    error_counts: Dict[str, int],
    latency_stats: Dict[str, Tuple[float, int]],
    active_sessions: int,
    report_path: str = "report.html",
) -> None:
    """Store computed metrics in SQLite and generate the HTML report.

    All database inserts use parameterised queries to prevent SQL injection.

    Args:
        db_path:        Path to the SQLite database file.
        error_counts:   Error message → count mapping from :func:`transform`.
        latency_stats:  Endpoint → (avg_ms, count) mapping from :func:`transform`.
        active_sessions: Number of currently active sessions.
        report_path:     Destination path for the HTML report.
    """
    now = datetime.now().isoformat()

    # --- Database -----------------------------------------------------------
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, (avg, _count) in latency_stats.items():
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()

    # --- HTML report --------------------------------------------------------
    html_parts: List[str] = []
    html_parts.append("<html>")
    html_parts.append("<head><title>System Report</title></head>")
    html_parts.append("<body>")
    html_parts.append("<h1>Error Summary</h1>")
    html_parts.append("<ul>")
    for err_msg, count in error_counts.items():
        html_parts.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    html_parts.append("</ul>")

    html_parts.append("<h2>API Latency</h2>")
    html_parts.append("<table border='1'>")
    html_parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, (avg, _) in latency_stats.items():
        html_parts.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )
    html_parts.append("</table>")

    html_parts.append("<h2>Active Sessions</h2>")
    html_parts.append(f"<p>{active_sessions} user(s) currently active</p>")
    html_parts.append("</body>")
    html_parts.append("</html>")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(html_parts))

    print(f"Job finished at {datetime.now()}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Extract → Transform → Load pipeline end-to-end."""
    # Ensure a log file exists for a fresh run
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    parsed = extract(LOG_FILE)
    error_counts, latency_stats, active_sessions = transform(parsed)
    load(DB_PATH, error_counts, latency_stats, active_sessions)


if __name__ == "__main__":
    main()