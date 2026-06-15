"""
Log processing pipeline: Extract → Transform → Load.

Parses server logs, aggregates metrics into SQLite, and produces an HTML report.
All configuration is driven by environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration (driven by environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """A single error event extracted from a log line."""
    timestamp: str
    message: str


@dataclass
class SessionEvent:
    """A user session event (login or logout)."""
    timestamp: str
    user_id: str
    action: str  # "logged in" or "logged out"


@dataclass
class ApiCall:
    """A single API call with its response time."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class AggregatedMetrics:
    """Aggregated data ready for reporting."""
    error_counts: dict[str, int] = field(default_factory=dict)
    api_latency_by_endpoint: dict[str, list[int]] = field(default_factory=dict)
    active_session_count: int = 0


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# Format: "2024-01-01 12:00:00 LEVEL message..."
_LOG_COMMON = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.*)$"
)

# INFO User <uid> <action>
_LOG_USER = re.compile(
    r"^User (?P<uid>\S+) (?P<action>logged in|logged out)$"
)

# INFO API /<endpoint> took <ms>ms
_LOG_API = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def extract_log_lines(log_path: str) -> list[str]:
    """
    Read all lines from the log file.

    Returns an empty list if the file does not exist.
    """
    path = Path(log_path)
    if not path.exists():
        return []
    return path.read_text().splitlines()


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def parse_log_entry(line: str) -> Optional[tuple[str, str, str]]:
    """
    Parse a single log line using regex.

    Returns:
        A 3-tuple of (timestamp, level, message) on success, or None if the
        line does not match the expected format.
    """
    match = _LOG_COMMON.match(line)
    if not match:
        return None
    return (
        match.group("timestamp"),
        match.group("level"),
        match.group("message"),
    )


def transform_logs(lines: list[str]) -> AggregatedMetrics:
    """
    Parse all log lines and aggregate into error counts, API latencies,
    and active session count.

    Args:
        lines: Raw lines read from the server log.

    Returns:
        An AggregatedMetrics instance with all computed data.
    """
    metrics = AggregatedMetrics()
    active_sessions: dict[str, str] = {}  # uid -> timestamp

    for raw_line in lines:
        parsed = parse_log_entry(raw_line)
        if parsed is None:
            continue

        timestamp, level, message = parsed

        if level == "ERROR":
            metrics.error_counts[message] = metrics.error_counts.get(message, 0) + 1

        elif level == "INFO":
            user_match = _LOG_USER.match(message)
            if user_match:
                uid = user_match.group("uid")
                action = user_match.group("action")
                if action == "logged in":
                    active_sessions[uid] = timestamp
                elif action == "logged out" and uid in active_sessions:
                    del active_sessions[uid]
                metrics.active_session_count = len(active_sessions)
                continue

            api_match = _LOG_API.match(message)
            if api_match:
                endpoint = api_match.group("endpoint")
                latency_ms = int(api_match.group("ms"))
                metrics.api_latency_by_endpoint.setdefault(endpoint, []).append(latency_ms)
                continue

        # level == "WARN": intentionally ignored for this report

    return metrics


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_init_db(conn: sqlite3.Connection) -> None:
    """Create the required tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_errors(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Insert aggregated error counts into the database using a parameterized query.

    Args:
        conn: Active SQLite connection.
        error_counts: Mapping from error message to occurrence count.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    # Parameterized query — safe from SQL injection
    cur.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in error_counts.items()],
    )
    conn.commit()


def load_api_metrics(
    conn: sqlite3.Connection, latency_by_endpoint: dict[str, list[int]]
) -> None:
    """
    Compute average latency per endpoint and insert using a parameterized query.

    Args:
        conn: Active SQLite connection.
        latency_by_endpoint: Mapping from endpoint to a list of latency values.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    rows = [
        (now, ep, sum(times) / len(times))
        for ep, times in latency_by_endpoint.items()
    ]
    cur.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def load_generate_report(
    output_path: str,
    error_counts: dict[str, int],
    latency_by_endpoint: dict[str, list[int]],
    active_session_count: int,
) -> None:
    """
    Render the HTML report covering error summary, API latency table,
    and active session count.

    Args:
        output_path: Destination file path for the HTML report.
        error_counts: Mapping from error message to occurrence count.
        latency_by_endpoint: Mapping from endpoint to list of latency values.
        active_session_count: Number of currently active sessions.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # Error summary
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    # API latency table
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in sorted(latency_by_endpoint.items()):
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{ep}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    # Active sessions
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines))


def run_pipeline() -> None:
    """
    Execute the full ETL pipeline.

    1. EXTRACT  — read log file
    2. TRANSFORM — parse and aggregate
    3. LOAD      — write DB + produce HTML report
    """
    # EXTRACT
    lines = extract_log_lines(LOG_FILE)

    # TRANSFORM
    metrics = transform_logs(lines)

    # LOAD
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")
    conn = sqlite3.connect(DB_PATH)
    load_init_db(conn)
    load_errors(conn, metrics.error_counts)
    load_api_metrics(conn, metrics.api_latency_by_endpoint)
    conn.close()

    load_generate_report(
        output_path="report.html",
        error_counts=metrics.error_counts,
        latency_by_endpoint=metrics.api_latency_by_endpoint,
        active_session_count=metrics.active_session_count,
    )

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap (creates a sample log when run standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        sample_log = (
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        Path(LOG_FILE).write_text(sample_log)

    run_pipeline()
