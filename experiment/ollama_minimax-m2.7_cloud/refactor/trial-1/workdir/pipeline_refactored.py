"""
Log processing pipeline that extracts server logs, transforms them into metrics,
and loads results into a SQLite database with HTML reporting.

Architecture follows the ETL pattern:
    Extract  -> parse_log_file()     reads and tokenizes log entries
    Transform -> build_error_summary() and compute_api_latency() aggregate data
    Load     -> store_metrics()      writes to DB; generate_report() produces HTML
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration (all loaded from environment with safe defaults for dev)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("PIPELINE_REPORT_FILE", "report.html")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")  # empty default; set via env


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ErrorEntry(NamedTuple):
    """An extracted ERROR record."""
    timestamp: str
    message: str


class ApiCallEntry(NamedTuple):
    """An extracted API call record."""
    timestamp: str
    endpoint: str
    duration_ms: int


# ERROR lines only (WARN is tracked separately in session events)
_ERROR_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"ERROR\s+(?P<message>.*)$"
)

# User event: "2024-01-01 12:00:00 INFO User 42 logged in"
_USER_EVENT_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO User (?P<user_id>\S+) (?P<action>logged in|logged out)"
)

# API call: "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
_API_CALL_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO API (?P<endpoint>\S+) took (?P<duration_ms>\d+)ms"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def parse_log_file(path: str) -> tuple[list[ErrorEntry], list[ApiCallEntry], dict[str, str]]:
    """
    Read ``path`` and extract structured records.

    Returns:
        Tuple of (error_records, api_call_records, active_sessions).

        ``active_sessions`` maps user_id -> timestamp of their last login.
        Users who logged out are removed from the map.
    """
    errors: list[ErrorEntry] = []
    api_calls: list[ApiCallEntry] = []
    sessions: dict[str, str] = {}  # user_id -> login timestamp

    if not os.path.exists(path):
        print(f"Log file not found: {path!r}; skipping extraction.")
        return errors, api_calls, sessions

    with open(path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")

            # ERROR lines
            m = _ERROR_LINE_RE.match(line)
            if m:
                errors.append(ErrorEntry(
                    timestamp=m.group("timestamp"),
                    message=m.group("message"),
                ))
                continue

            # User auth events
            m = _USER_EVENT_RE.match(line)
            if m:
                user_id = m.group("user_id")
                action = m.group("action")
                timestamp = m.group("timestamp")
                if action == "logged in":
                    sessions[user_id] = timestamp
                elif action == "logged out":
                    sessions.pop(user_id, None)
                continue

            # API calls
            m = _API_CALL_RE.match(line)
            if m:
                api_calls.append(ApiCallEntry(
                    timestamp=m.group("timestamp"),
                    endpoint=m.group("endpoint"),
                    duration_ms=int(m.group("duration_ms")),
                ))
                continue

    return errors, api_calls, sessions


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def build_error_summary(errors: list[ErrorEntry]) -> dict[str, int]:
    """
    Count occurrences of each unique error message.

    Returns:
        Mapping of message -> total count, sorted descending by count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def compute_api_latency(api_calls: list[ApiCallEntry]) -> dict[str, float]:
    """
    Compute average latency per endpoint.

    Returns:
        Mapping of endpoint -> average duration in ms, rounded to 1 decimal.
    """
    totals: dict[str, list[int]] = {}
    for call in api_calls:
        totals.setdefault(call.endpoint, []).append(call.duration_ms)

    return {
        ep: round(sum(times) / len(times), 1)
        for ep, times in totals.items()
    }


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def store_metrics(
    db_path: str,
    errors: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """
    Persist aggregated metrics into the SQLite database.

    Uses parameterized queries to prevent SQL injection.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            dt      TEXT,
            message TEXT,
            count   INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt       TEXT,
            endpoint TEXT,
            avg_ms   REAL
        )
    """)

    now = datetime.datetime.now().isoformat()

    for msg, count in errors.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(
    report_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_session_count: int,
) -> None:
    """
    Write the HTML report to ``report_path``.

    Produces the same sections as the original pipeline:
        - Error Summary (bullet list)
        - API Latency table (endpoint, avg ms)
        - Active Sessions count
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"  <title>System Report — {now}</title>",
        "</head>",
        "<body>",
        f"  <h1>System Report — {now}</h1>",
        "",
        "  <h2>Error Summary</h2>",
        "  <ul>",
    ]

    if error_summary:
        for msg, count in error_summary.items():
            lines.append(f"    <li><b>{msg}</b>: {count} occurrences</li>")
    else:
        lines.append("    <li>No errors recorded.</li>")

    lines.extend([
        "  </ul>",
        "",
        "  <h2>API Latency</h2>",
        "  <table border='1'>",
        "    <tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if api_latency:
        for endpoint, avg_ms in sorted(api_latency.items()):
            lines.append(f"    <tr><td>{endpoint}</td><td>{avg_ms}</td></tr>")
    else:
        lines.append("    <tr><td colspan='2'>No API calls recorded.</td></tr>")

    lines.extend([
        "  </table>",
        "",
        "  <h2>Active Sessions</h2>",
        f"  <p>{active_session_count} user(s) currently active</p>",
        "",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))

    print(f"Report written to {report_path!r}")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract, transform, load, report.

    Reads configuration from environment variables (see module constants).
    """
    print(f"[{datetime.datetime.now()}] Pipeline starting...")

    # EXTRACT
    errors, api_calls, active_sessions = parse_log_file(LOG_FILE)
    print(f"Extracted {len(errors)} errors, {len(api_calls)} API calls, "
          f"{len(active_sessions)} active sessions.")

    # TRANSFORM
    error_summary = build_error_summary(errors)
    api_latency = compute_api_latency(api_calls)

    # LOAD — database
    store_metrics(DB_PATH, error_summary, api_latency)

    # LOAD — HTML report
    generate_report(REPORT_FILE, error_summary, api_latency, len(active_sessions))

    print(f"[{datetime.datetime.now()}] Pipeline finished.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_pipeline()
