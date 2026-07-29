"""Refactored server-log pipeline: Extract → Transform → Load.

Reads server logs, parses structured events with regex, aggregates metrics,
persists results to SQLite with parameterized queries, and generates an HTML
report.  All configuration is sourced from environment variables.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration — environment variables with sensible defaults
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")
REPORT_PATH: str = os.getenv("REPORT_PATH", "report.html")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user session event (login/logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCallEvent:
    """An API call with latency information."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarnEvent:
    """A WARN-level log entry."""

    timestamp: str
    message: str


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# "2024-01-01 12:05:00 ERROR Database timeout"
RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+ERROR\s+(?P<msg>.+)$"
)

# "2024-01-01 12:00:00 INFO User 42 logged in"
RE_USER = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

# "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
RE_API = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)

# "2024-01-01 12:09:00 WARN Memory usage at 87%"
RE_WARN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+WARN\s+(?P<msg>.+)$"
)


# ---------------------------------------------------------------------------
# Extract — read and parse log lines
# ---------------------------------------------------------------------------


def extract_log_entries(
    log_path: str,
) -> Tuple[List[ErrorEvent | UserEvent | WarnEvent], Dict[str, str], List[ApiCallEvent]]:
    """Read the server log and parse structured events.

    Each line is matched against regex patterns for ERROR, User, API, and WARN
    entries.  Unrecognised lines are silently skipped.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple of (general_events, active_sessions, api_calls).
        *general_events* holds ErrorEvent and WarnEvent items.
        *active_sessions* maps user_id to login timestamp.
        *api_calls* holds ApiCallEvent items.
    """
    events: List[ErrorEvent | UserEvent | WarnEvent] = []
    sessions: Dict[str, str] = {}
    api_calls: List[ApiCallEvent] = []

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return events, sessions, api_calls

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")

            m = RE_USER.match(line)
            if m:
                uid = m.group("uid")
                action = m.group("action").strip()
                if "logged in" in action:
                    sessions[uid] = m.group("ts")
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid, None)
                events.append(
                    UserEvent(timestamp=m.group("ts"), user_id=uid, action=action)
                )
                continue

            m = RE_API.match(line)
            if m:
                api_calls.append(
                    ApiCallEvent(
                        timestamp=m.group("ts"),
                        endpoint=m.group("endpoint"),
                        latency_ms=int(m.group("ms")),
                    )
                )
                continue

            m = RE_ERROR.match(line)
            if m:
                events.append(
                    ErrorEvent(timestamp=m.group("ts"), message=m.group("msg").strip())
                )
                continue

            m = RE_WARN.match(line)
            if m:
                events.append(
                    WarnEvent(timestamp=m.group("ts"), message=m.group("msg").strip())
                )
                continue

    return events, sessions, api_calls


# ---------------------------------------------------------------------------
# Transform — aggregate parsed data into report-ready summaries
# ---------------------------------------------------------------------------


def transform_data(
    events: List[ErrorEvent | UserEvent | WarnEvent],
    sessions: Dict[str, str],
    api_calls: List[ApiCallEvent],
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Aggregate raw events into summary structures.

    Args:
        events: Parsed log events (ErrorEvent, WarnEvent, etc.).
        sessions: Active user sessions (user_id → timestamp).
        api_calls: API call events with latency data.

    Returns:
        A tuple of (error_counts, endpoint_latencies, active_session_count).
        *error_counts* maps error message → occurrence count.
        *endpoint_latencies* maps endpoint → list of latency values.
        *active_session_count* is the number of currently active sessions.
    """
    error_counts: Dict[str, int] = {}
    for event in events:
        if isinstance(event, ErrorEvent):
            error_counts[event.message] = error_counts.get(event.message, 0) + 1

    endpoint_latencies: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.latency_ms)

    return error_counts, endpoint_latencies, len(sessions)


# ---------------------------------------------------------------------------
# Load — persist to database and generate HTML report
# ---------------------------------------------------------------------------


def load_report(
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_session_count: int,
    db_path: str = DB_PATH,
    report_path: str = REPORT_PATH,
) -> None:
    """Write aggregated data to SQLite and generate an HTML report.

    Uses parameterised queries throughout to prevent SQL injection.

    Args:
        error_counts: Error message → count mapping.
        endpoint_latencies: Endpoint → list of latency values.
        active_session_count: Number of active sessions.
        db_path: Path to the SQLite database file.
        report_path: Path for the output HTML report.
    """
    now = datetime.datetime.now().isoformat()

    # --- Persist to SQLite ---
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

    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    # --- Generate HTML report ---
    lines: List[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Report written to {report_path}")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    events, sessions, api_calls = extract_log_entries(LOG_FILE)
    error_counts, endpoint_latencies, active_session_count = transform_data(
        events, sessions, api_calls
    )
    load_report(error_counts, endpoint_latencies, active_session_count)


if __name__ == "__main__":
    # Create a sample log when running standalone without an existing file,
    # so the script works out-of-the-box for testing.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()