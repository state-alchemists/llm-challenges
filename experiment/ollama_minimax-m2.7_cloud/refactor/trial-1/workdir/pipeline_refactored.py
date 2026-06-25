"""
Log processing pipeline — ETL pattern for server log analysis.

Extracts structured events from log files, transforms them into aggregated
metrics, loads results into a SQLite database, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    """A parsed ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A parsed user action (login/logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEvent:
    """A parsed API call entry."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class LatencyStats:
    """Aggregated latency for a single endpoint."""

    endpoint: str
    avg_ms: float
    count: int


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("PIPELINE_REPORT_FILE", "report.html")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load)
# ---------------------------------------------------------------------------

# Example line: "2024-01-01 12:00:00 INFO User 42 logged in"
RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO User (?P<user_id>\S+) (?P<action>logged in|logged out)$"
)

# Example line: "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)

# Example line: "2024-01-01 12:05:00 ERROR Database timeout"
RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"ERROR (?P<message>.+)$"
)

# Example line: "2024-01-01 12:09:00 WARN Memory usage at 87%"
RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"WARN (?P<message>.+)$"
)


# ---------------------------------------------------------------------------
# EXTRACT — parse log lines into structured events
# ---------------------------------------------------------------------------


def parse_log_file(path: str) -> tuple[list[ErrorEvent], list[UserEvent], list[ApiEvent]]:
    """
    Parse a log file and return three lists of structured events.

    Returns
    -------
    Tuple of (errors, user_events, api_events)
    """
    errors: list[ErrorEvent] = []
    user_events: list[UserEvent] = []
    api_events: list[ApiEvent] = []

    if not os.path.exists(path):
        return errors, user_events, api_events

    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            if (m := RE_ERROR.match(line)) is not None:
                errors.append(ErrorEvent(timestamp=m.group("timestamp"), message=m.group("message")))
            elif (m := RE_USER.match(line)) is not None:
                user_events.append(
                    UserEvent(
                        timestamp=m.group("timestamp"),
                        user_id=m.group("user_id"),
                        action=m.group("action"),
                    )
                )
            elif (m := RE_API.match(line)) is not None:
                api_events.append(
                    ApiEvent(
                        timestamp=m.group("timestamp"),
                        endpoint=m.group("endpoint"),
                        latency_ms=int(m.group("ms")),
                    )
                )
            # WARN lines are not currently stored; placeholder for future use.

    return errors, user_events, api_events


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate raw events into metrics
# ---------------------------------------------------------------------------


def count_errors_by_message(errors: list[ErrorEvent]) -> dict[str, int]:
    """
    Group error events by message text and count occurrences.

    Returns
    -------
    Mapping from error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for e in errors:
        counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def aggregate_api_latency(api_events: list[ApiEvent]) -> list[LatencyStats]:
    """
    Compute average latency per endpoint across all API events.

    Returns
    -------
    List of LatencyStats sorted by endpoint name.
    """
    by_endpoint: dict[str, list[int]] = {}
    for ev in api_events:
        by_endpoint.setdefault(ev.endpoint, []).append(ev.latency_ms)

    stats: list[LatencyStats] = []
    for endpoint, times in sorted(by_endpoint.items()):
        avg = sum(times) / len(times)
        stats.append(LatencyStats(endpoint=endpoint, avg_ms=avg, count=len(times)))

    return stats


def count_active_sessions(user_events: list[UserEvent]) -> int:
    """
    Count users with an open "logged in" session (no subsequent logout).

    A user is considered active if they have at least one login event
    that is not balanced by a later logout event.
    """
    sessions: dict[str, int] = {}  # user_id -> login count

    for ev in user_events:
        if ev.action == "logged in":
            sessions[ev.user_id] = sessions.get(ev.user_id, 0) + 1
        elif ev.action == "logged out" and ev.user_id in sessions:
            sessions[ev.user_id] -= 1
            if sessions[ev.user_id] <= 0:
                del sessions[ev.user_id]

    return len(sessions)


# ---------------------------------------------------------------------------
# LOAD — write to database and produce HTML report
# ---------------------------------------------------------------------------


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create or verify the required metric tables exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_error_counts(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Persist aggregated error counts to the database using parameterized queries.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active database connection.
    error_counts : dict[str, int]
        Mapping from error message to occurrence count.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def load_api_metrics(conn: sqlite3.Connection, stats: list[LatencyStats]) -> None:
    """
    Persist aggregated API latency metrics using parameterized queries.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active database connection.
    stats : list[LatencyStats]
        Per-endpoint latency aggregates.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    for s in stats:
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, s.endpoint, s.avg_ms),
        )
    conn.commit()


def generate_html_report(
    error_counts: dict[str, int],
    latency_stats: list[LatencyStats],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Write the HTML report covering errors, API latency, and active sessions.

    Parameters
    ----------
    error_counts : dict[str, int]
        Error message -> count mapping.
    latency_stats : list[LatencyStats]
        Aggregated API latency per endpoint.
    active_sessions : int
        Number of currently active user sessions.
    output_path : str
        Destination file path for the HTML report.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        f"<p><i>Generated at {now}</i></p>",
        "",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if error_counts:
        for msg, count in sorted(error_counts.items()):
            lines.append(f"  <li><b>{msg}</b>: {count} occurrence(s)</li>")
    else:
        lines.append("  <li>No errors recorded.</li>")

    lines.extend([
        "</ul>",
        "",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "  <tr><th>Endpoint</th><th>Avg (ms)</th><th>Calls</th></tr>",
    ])

    if latency_stats:
        for s in latency_stats:
            lines.append(
                f"  <tr><td>{s.endpoint}</td>"
                f"<td>{round(s.avg_ms, 1)}</td>"
                f"<td>{s.count}</td></tr>"
            )
    else:
        lines.append("  <tr><td colspan='2'>No API calls recorded.</td></tr>")

    lines.extend([
        "</table>",
        "",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract → transform → load → report.

    Configuration is read from environment variables (with sensible defaults).
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT}...")

    # EXTRACT
    errors, user_events, api_events = parse_log_file(LOG_FILE)
    print(f"Extracted {len(errors)} errors, {len(user_events)} user events, "
          f"{len(api_events)} API calls from '{LOG_FILE}'.")

    # TRANSFORM
    error_counts = count_errors_by_message(errors)
    latency_stats = aggregate_api_latency(api_events)
    active_sessions = count_active_sessions(user_events)

    # LOAD — database
    conn = sqlite3.connect(DB_PATH)
    ensure_tables(conn)
    load_error_counts(conn, error_counts)
    load_api_metrics(conn, latency_stats)
    conn.close()
    print(f"Metrics written to '{DB_PATH}'.")

    # LOAD — report
    generate_html_report(error_counts, latency_stats, active_sessions, REPORT_FILE)
    print(f"Report written to '{REPORT_FILE}'.")

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a sample log file when none exists (for demo / first-run)
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as f:
            f.write("\n".join(sample_lines) + "\n")

    run_pipeline()
