"""
Server log processing pipeline (ETL).

Extracts events from server logs, aggregates error counts and API latency,
loads results into SQLite, and produces an HTML report.

Usage:
    export LOG_FILE="server.log"
    export DB_PATH="metrics.db"
    export DB_HOST="localhost"
    export DB_PORT="5432"
    export DB_USER="admin"
    export DB_PASS="secret"
    python pipeline_refactored.py
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Literal, cast


# ---------------------------------------------------------------------------
# Configuration (all loaded from environment variables)
# ---------------------------------------------------------------------------

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ---------------------------------------------------------------------------
# Event types — discriminated union via 'kind' tag
# ---------------------------------------------------------------------------

class ErrorEvent(dict):
    __slots__ = ()
    kind: Literal["error"] = "error"
    timestamp: str
    message: str


class UserEvent(dict):
    __slots__ = ()
    kind: Literal["user"] = "user"
    timestamp: str
    uid: str
    action: str


class ApiEvent(dict):
    __slots__ = ()
    kind: Literal["api"] = "api"
    timestamp: str
    endpoint: str
    latency_ms: int


class WarnEvent(dict):
    __slots__ = ()
    kind: Literal["warn"] = "warn"
    timestamp: str
    message: str


LogEvent = ErrorEvent | UserEvent | ApiEvent | WarnEvent


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load)
# ---------------------------------------------------------------------------

# Example: "2024-01-01 12:00:00 INFO User 42 logged in"
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO) "
    r"User (?P<uid>\S+) "
    r"(?P<action>.*)$"
)

# Example: "2024-01-01 12:05:00 ERROR Database timeout"
_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR) "
    r"(?P<message>.*)$"
)

# Example: "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO) "
    r"API (?P<endpoint>\S+) "
    r"took (?P<latency_ms>\d+)ms$"
)

# Example: "2024-01-01 12:09:00 WARN Memory usage at 87%"
_RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>WARN) "
    r"(?P<message>.*)$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> LogEvent | None:
    """
    Parse a single log line and return a typed event dict, or None if the
    line format is not recognised.

    Parameters
    ----------
    line : str
        Raw line from the log file (no trailing newline).

    Returns
    -------
    LogEvent | None
        Typed event dict for known log levels, or None for unrecognised lines.
    """
    line = line.rstrip("\n")

    m = _RE_ERROR.match(line)
    if m:
        e = ErrorEvent()
        e["timestamp"] = m["timestamp"]
        e["kind"] = "error"
        e["message"] = m["message"]
        return e

    m = _RE_USER.match(line)
    if m:
        e = UserEvent()
        e["timestamp"] = m["timestamp"]
        e["kind"] = "user"
        e["uid"] = m["uid"]
        e["action"] = m["action"]
        return e

    m = _RE_API.match(line)
    if m:
        e = ApiEvent()
        e["timestamp"] = m["timestamp"]
        e["kind"] = "api"
        e["endpoint"] = m["endpoint"]
        e["latency_ms"] = int(m["latency_ms"])
        return e

    m = _RE_WARN.match(line)
    if m:
        e = WarnEvent()
        e["timestamp"] = m["timestamp"]
        e["kind"] = "warn"
        e["message"] = m["message"]
        return e

    return None


def extract_from_log(path: str) -> tuple[list[ErrorEvent], list[ApiEvent], dict[str, str]]:
    """
    Read the log file at *path* and extract all relevant events.

    Parameters
    ----------
    path : str
        Path to the server log file.

    Returns
    -------
    tuple[list[ErrorEvent], list[ApiEvent], dict[str, str]]
        Tuple of:
        - error_events  : list of ERROR event dicts
        - api_events    : list of API latency event dicts
        - active_sessions: dict mapping user ID -> login timestamp
    """
    error_events: list[ErrorEvent] = []
    api_events: list[ApiEvent] = []
    active_sessions: dict[str, str] = {}

    if not os.path.exists(path):
        return error_events, api_events, active_sessions

    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            event = parse_log_line(raw_line)
            if event is None:
                continue

            match event["kind"]:
                case "error":
                    error_events.append(cast(ErrorEvent, event))
                case "api":
                    api_events.append(cast(ApiEvent, event))
                case "user":
                    uid = event["uid"]
                    action = event["action"]
                    if "logged in" in action:
                        active_sessions[uid] = event["timestamp"]
                    elif "logged out" in action and uid in active_sessions:
                        del active_sessions[uid]

    return error_events, api_events, active_sessions


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform_error_counts(events: list[ErrorEvent]) -> dict[str, int]:
    """
    Aggregate error events into a message -> count mapping.

    Parameters
    ----------
    events : list[ErrorEvent]
        Raw ERROR events extracted from the log.

    Returns
    -------
    dict[str, int]
        Error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for e in events:
        msg = e["message"]
        counts[msg] = counts.get(msg, 0) + 1
    return counts


def transform_api_latency(events: list[ApiEvent]) -> dict[str, list[int]]:
    """
    Group API events by endpoint and collect latency samples.

    Parameters
    ----------
    events : list[ApiEvent]
        Raw API INFO events extracted from the log.

    Returns
    -------
    dict[str, list[int]]
        Endpoint to list of latency (ms) samples.
    """
    buckets: dict[str, list[int]] = {}
    for e in events:
        buckets.setdefault(e["endpoint"], []).append(e["latency_ms"])
    return buckets


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    timestamp: datetime.datetime,
) -> None:
    """
    Persist error counts and API latency aggregates to the SQLite database.

    Uses parameterised queries throughout to prevent SQL injection.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    error_counts : dict[str, int]
        Error message -> count mapping.
    api_latency : dict[str, list[int]]
        Endpoint -> latency samples mapping.
    timestamp : datetime.datetime
        Timestamp to record in each row.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Parameterised INSERT — safe against injection
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (timestamp.isoformat(), msg, count),
        )

    for endpoint, samples in api_latency.items():
        avg = sum(samples) / len(samples)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (timestamp.isoformat(), endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions_count: int,
    output_path: str,
) -> None:
    """
    Write the HTML report to *output_path*.

    Parameters
    ----------
    error_counts : dict[str, int]
        Error message -> count mapping.
    api_latency : dict[str, list[int]]
        Endpoint -> latency samples mapping.
    active_sessions_count : int
        Number of currently active (logged-in) sessions.
    output_path : str
        Destination file path for the HTML report.
    """
    lines: list[str] = []

    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # Error summary
    lines.append("<h1>Error Summary</h1>")
    if error_counts:
        lines.append("<ul>")
        for msg, count in error_counts.items():
            lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
        lines.append("</ul>")
    else:
        lines.append("<p>No errors recorded.</p>")

    # API latency table
    lines.append("<h2>API Latency</h2>")
    if api_latency:
        lines.append("<table border='1'>")
        lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
        for endpoint, samples in api_latency.items():
            avg = sum(samples) / len(samples)
            lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
        lines.append("</table>")
    else:
        lines.append("<p>No API calls recorded.</p>")

    # Active sessions
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions_count} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_etl() -> None:
    """
    Run the full Extract → Transform → Load pipeline end-to-end.
    """
    ts = datetime.datetime.now()
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # EXTRACT
    errors, api_events, active_sessions = extract_from_log(LOG_FILE)

    # TRANSFORM
    error_counts = transform_error_counts(errors)
    api_latency = transform_api_latency(api_events)

    # LOAD → DB
    load_to_db(DB_PATH, error_counts, api_latency, ts)

    # LOAD → HTML report
    generate_report(error_counts, api_latency, len(active_sessions), "report.html")

    print(f"Job finished at {ts.isoformat()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Seed a sample log when the file is absent (convenience for first run)
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sample_lines) + "\n")

    run_etl()
