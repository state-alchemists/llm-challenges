#!/usr/bin/env python3
"""
Log processing pipeline that extracts events from server logs,
aggregates metrics, stores them in a SQLite database, and produces an HTML report.

Configuration is driven entirely by environment variables (see Config class).
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

@dataclass
class Config:
    """Pipeline configuration sourced from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> "Config":
        """Read configuration from environment variables with sensible defaults."""
        return cls(
            db_path=os.environ.get("DB_PATH", "metrics.db"),
            log_file=os.environ.get("LOG_FILE", "server.log"),
            db_host=os.environ.get("DB_HOST", "localhost"),
            db_port=int(os.environ.get("DB_PORT", "5432")),
            db_user=os.environ.get("DB_USER", "admin"),
            db_pass=os.environ.get("DB_PASS", ""),
        )


# -------------------------------------------------------------------
# Data models
# -------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A parsed ERROR-level log line."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A parsed user action (login/logout)."""
    timestamp: str
    user_id: str
    action: str  # "logged in" or "logged out"


@dataclass
class ApiCall:
    """A parsed API latency log line."""
    timestamp: str
    endpoint: str
    duration_ms: int


# -------------------------------------------------------------------
# Extract — read and parse log file
# -------------------------------------------------------------------

# Regex patterns for each log line format
_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"User (?P<user_id>\S+) (?P<action>logged in|logged out)$"
)
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"API (?P<endpoint>\S+) took (?P<duration_ms>\d+)ms$"
)
_RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.+)$"
)


def _seed_sample_log(log_file: str) -> None:
    """Create a minimal sample log when the log file is absent (preserves original behaviour)."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(log_file, "w") as fh:
        fh.writelines(sample_lines)


def extract_events(log_file: str) -> tuple[list[ErrorEntry], list[UserEvent], list[ApiCall]]:
    """
    Parse the log file and return structured events.

    Returns:
        Tuple of (errors, user_events, api_calls) in declaration order.
    """
    errors: list[ErrorEntry] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []

    if not os.path.exists(log_file):
        _seed_sample_log(log_file)

    with open(log_file, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue

            if (m := _RE_ERROR.match(line)) is not None:
                errors.append(ErrorEntry(
                    timestamp=m.group("timestamp"),
                    message=m.group("message"),
                ))
            elif (m := _RE_USER.match(line)) is not None:
                user_events.append(UserEvent(
                    timestamp=m.group("timestamp"),
                    user_id=m.group("user_id"),
                    action=m.group("action"),
                ))
            elif (m := _RE_API.match(line)) is not None:
                api_calls.append(ApiCall(
                    timestamp=m.group("timestamp"),
                    endpoint=m.group("endpoint"),
                    duration_ms=int(m.group("duration_ms")),
                ))
            # WARN lines are accepted but not aggregated in this pipeline's output.

    return errors, user_events, api_calls


# -------------------------------------------------------------------
# Transform — aggregate raw events into reportable metrics
# -------------------------------------------------------------------

def transform_metrics(
    errors: list[ErrorEntry],
    user_events: list[UserEvent],
    api_calls: list[ApiCall],
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """
    Compute error counts, per-endpoint latency lists, and active session count.

    Returns:
        (error_counts, endpoint_latencies, active_session_count)
    """
    # Error frequency table
    error_counts: dict[str, int] = {}
    for err in errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # Per-endpoint latency samples
    endpoint_latencies: dict[str, list[int]] = {}
    for call in api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.duration_ms)

    # Active sessions: login without a subsequent logout
    sessions: dict[str, str] = {}
    for evt in user_events:
        if evt.action == "logged in":
            sessions[evt.user_id] = evt.timestamp
        elif evt.action == "logged out" and evt.user_id in sessions:
            del sessions[evt.user_id]

    return error_counts, endpoint_latencies, len(sessions)


# -------------------------------------------------------------------
# Load — write to database and emit HTML report
# -------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load_db(conn: sqlite3.Connection, error_counts: dict[str, int], endpoint_latencies: dict[str, list[int]]) -> None:
    """
    Persist aggregated metrics into SQLite using parameterised queries.

    Uses ? placeholders to prevent SQL injection (all user-controlled values
    are bound as parameters, never interpolated into the query string).
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, durations in endpoint_latencies.items():
        avg = sum(durations) / len(durations)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()


def render_report(error_counts: dict[str, int], endpoint_latencies: dict[str, list[int]], active_sessions: int) -> str:
    """
    Produce the HTML report string with the same structure as the original pipeline.

    Sections: Error Summary, API Latency table, Active Session count.
    """
    buf = ["<html>\n<head><title>System Report</title></head>\n<body>\n"]

    # Error Summary
    buf.append("<h1>Error Summary</h1>\n<ul>\n")
    for err_msg, count in error_counts.items():
        buf.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>\n")
    buf.append("</ul>\n")

    # API Latency table
    buf.append("<h2>API Latency</h2>\n<table border='1'>\n")
    buf.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n")
    for ep, durations in endpoint_latencies.items():
        avg = sum(durations) / len(durations)
        buf.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n")
    buf.append("</table>\n")

    # Active Sessions
    buf.append("<h2>Active Sessions</h2>\n")
    buf.append(f"<p>{active_sessions} user(s) currently active</p>\n")
    buf.append("</body>\n</html>")

    return "".join(buf)


def write_report(output_path: str, html: str) -> None:
    """Write the HTML report to disk."""
    with open(output_path, "w") as fh:
        fh.write(html)


# -------------------------------------------------------------------
# Main pipeline orchestration
# -------------------------------------------------------------------

def run_pipeline(config: Optional[Config] = None) -> None:
    """
    Execute the full Extract → Transform → Load pipeline.

    Args:
        config: Optional Config instance. If omitted, reads from environment.
    """
    if config is None:
        config = Config.from_env()

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    # ── EXTRACT ──────────────────────────────────────────────────────
    errors, user_events, api_calls = extract_events(config.log_file)

    # ── TRANSFORM ────────────────────────────────────────────────────
    error_counts, endpoint_latencies, active_sessions = transform_metrics(
        errors, user_events, api_calls
    )

    # ── LOAD (database) ───────────────────────────────────────────────
    conn = sqlite3.connect(config.db_path)
    try:
        init_db(conn)
        load_db(conn, error_counts, endpoint_latencies)
    finally:
        conn.close()

    # ── LOAD (report) ─────────────────────────────────────────────────
    html = render_report(error_counts, endpoint_latencies, active_sessions)
    write_report("report.html", html)

    print(f"Job finished at {datetime.datetime.now()}")


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

if __name__ == "__main__":
    run_pipeline()
