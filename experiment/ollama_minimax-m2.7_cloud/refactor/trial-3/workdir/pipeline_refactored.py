"""
Server log processing pipeline.

ETL pipeline that extracts log data, transforms it into metrics,
and loads results into SQLite with HTML report generation.
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration (all from environment variables with safe defaults)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ErrorEntry(TypedDict):
    """An error log entry."""
    dt: str
    t: str
    m: str


class UserEntry(TypedDict):
    """A user session log entry."""
    dt: str
    t: str
    u: str
    a: str


class ApiCall(TypedDict):
    """An API call log entry."""
    d: str
    endpoint: str
    ms: int


class LogData(TypedDict):
    """Structured log data returned by the extractor."""
    errors: list[ErrorEntry]
    sessions: dict[str, str]
    api_calls: list[ApiCall]


# ---------------------------------------------------------------------------
# Regex patterns (compiled once, reused)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(r"^(\S+)\s+(\S+)\s+ERROR\s+(.+)$")
_RE_USER = re.compile(r"^(\S+)\s+(\S+)\s+INFO\s+User\s+(\S+)\s+(.+)$")
_RE_API = re.compile(r"^(\S+)\s+(\S+)\s+INFO\s+API\s+(\S+)\s+took\s+(\d+)ms$")
_RE_WARN = re.compile(r"^(\S+)\s+(\S+)\s+WARN\s+(.+)$")


# ---------------------------------------------------------------------------
# EXTRACT — parse log file into structured data
# ---------------------------------------------------------------------------

def extract_log_data(log_path: str) -> LogData:
    """
    Parse a server log file and extract errors, sessions, and API calls.

    Args:
        log_path: Path to the server log file.

    Returns:
        A LogData dict with keys: errors (list), sessions (dict), api_calls (list).

    Raises:
        FileNotFoundError: If log_path does not exist.
    """
    errors: list[ErrorEntry] = []
    sessions: dict[str, str] = {}
    api_calls: list[ApiCall] = []

    with open(log_path, "r") as f:
        for line in f:
            line = line.rstrip("\n")

            # ERROR lines
            m = _RE_ERROR.match(line)
            if m:
                dt = f"{m.group(1)} {m.group(2)}"
                message = m.group(3)
                errors.append({"d": dt, "t": "ERR", "m": message})
                continue

            # USER session lines (INFO with "User NNN" pattern)
            m = _RE_USER.match(line)
            if m:
                dt = f"{m.group(1)} {m.group(2)}"
                uid = m.group(3)
                action = m.group(4)
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]
                continue

            # API latency lines (INFO with "API /endpoint took Nms" pattern)
            m = _RE_API.match(line)
            if m:
                dt = f"{m.group(1)} {m.group(2)}"
                endpoint = m.group(3)
                duration_ms = int(m.group(4))
                api_calls.append({"d": dt, "endpoint": endpoint, "ms": duration_ms})
                continue

            # WARN lines
            m = _RE_WARN.match(line)
            if m:
                dt = f"{m.group(1)} {m.group(2)}"
                message = m.group(3)
                errors.append({"d": dt, "t": "WARN", "m": message})

    return {"errors": errors, "sessions": sessions, "api_calls": api_calls}


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate parsed data into summary statistics
# ---------------------------------------------------------------------------

def transform_data(raw: LogData) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """
    Compute error counts, API latency averages, and active session count.

    Args:
        raw: Structured log data from extract_log_data().

    Returns:
        A 3-tuple of:
        - error_counts: {message: total_occurrences}
        - api_latency: {endpoint: [list of durations in ms]}
        - active_sessions: int count of still-open sessions
    """
    # Aggregate errors and warnings by message
    error_counts: dict[str, int] = {}
    for entry in raw["errors"]:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    # Aggregate API call durations by endpoint
    api_latency: dict[str, list[int]] = {}
    for call in raw["api_calls"]:
        endpoint = call["endpoint"]
        api_latency.setdefault(endpoint, []).append(call["ms"])

    return error_counts, api_latency, len(raw["sessions"])


# ---------------------------------------------------------------------------
# LOAD — write to SQLite and generate HTML report
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
    report_path: str = "report.html",
) -> None:
    """
    Persist metrics to SQLite and write the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Aggregated error message -> count map.
        api_latency: Endpoint -> list of durations in ms.
        active_sessions: Number of currently active sessions.
        report_path: Destination path for the HTML report.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
    """)

    now = datetime.datetime.now().isoformat()

    # Parameterized INSERT for errors (fixes SQL injection)
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    # Parameterized INSERT for API metrics
    for ep, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    _write_html_report(report_path, error_counts, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


def _write_html_report(
    path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """
    Render the metrics as a self-contained HTML document.

    Args:
        path: Destination file path.
        error_counts: Error message -> count map.
        api_latency: Endpoint -> durations in ms map.
        active_sessions: Number of active sessions.
    """
    lines: list[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(f"  <li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"  <tr><td>{ep}</td><td>{avg}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract → transform → load.

    All configuration is read from environment variables (or their defaults).
    Prints progress messages to stdout.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    raw = extract_log_data(LOG_FILE)
    error_counts, api_latency, active_sessions = transform_data(raw)
    load_to_db(DB_PATH, error_counts, api_latency, active_sessions)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        # Bootstrap a minimal sample log so the pipeline can run out of the box
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()