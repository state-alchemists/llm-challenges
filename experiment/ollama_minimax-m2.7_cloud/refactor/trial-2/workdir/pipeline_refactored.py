#!/usr/bin/env python3
"""
Server log processing pipeline.

Extracts events from server logs, computes error summaries and API latency
metrics, stores them in a SQLite database, and generates an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Any, Protocol


# ─────────────────────────────────────────────────────────────────────────────
# Configuration (from environment)
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "password123")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: str = os.environ.get("PIPELINE_DB_PORT", "5432")


# ─────────────────────────────────────────────────────────────────────────────
# Types
#
# LogEntryProtocol is the interface that every parsed entry dict satisfies:
#   - "type"   : discriminator string  ("ERR" | "USR" | "WARN" | "API")
#   - "timestamp" : ISO-format datetime string
# Specific entry types add their own fields.
# ParsedLog is simply a list of such dicts (typed as dict[str, Any] so the
# type checker doesn't complain when we access fields that not every variant
# has — runtime code does explicit type checks via the "type" discriminator).
# ─────────────────────────────────────────────────────────────────────────────

class LogEntryProtocol(Protocol):
    """Interface every log entry dict conforms to."""
    def __getitem__(self, key: str) -> Any: ...


ParsedLog = list[dict[str, Any]]


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN)"
    r"(?:\s+(?P<body>.+))?$"
)

_RE_USER_ACTION = re.compile(
    r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$"
)

_RE_API_CALL = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACT — read and parse log file
# ─────────────────────────────────────────────────────────────────────────────

def parse_log_file(path: str) -> ParsedLog:
    """
    Read *path* line by line and return a list of typed log entries.

    Each entry is a TypedDict with at least a ``type`` field:
    - ERROR  → {timestamp, type, message}
    - WARN   → {timestamp, type, message}
    - INFO + User → {timestamp, type, user_id, action}
    - INFO + API  → {timestamp, endpoint, ms}
    """
    entries: ParsedLog = []
    if not os.path.exists(path):
        return entries

    with open(path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _RE_LOG_LINE.match(line)
            if not m:
                continue

            ts = m.group("timestamp")
            level = m.group("level")
            body = m.group("body") or ""

            if level == "ERROR":
                entries.append({"timestamp": ts, "type": "ERR", "message": body})

            elif level == "WARN":
                entries.append({"timestamp": ts, "type": "WARN", "message": body})

            elif level == "INFO":
                user_m = _RE_USER_ACTION.match(body)
                if user_m:
                    entries.append({
                        "timestamp": ts,
                        "type": "USR",
                        "user_id": user_m.group("user_id"),
                        "action": user_m.group("action"),
                    })
                    continue

                api_m = _RE_API_CALL.match(body)
                if api_m:
                    entries.append({
                        "timestamp": ts,
                        "type": "API",
                        "endpoint": api_m.group("endpoint"),
                        "ms": int(api_m.group("ms")),
                    })

    return entries


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORM — aggregate raw entries into reportable metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_error_summary(entries: ParsedLog) -> dict[str, int]:
    """
    Return a mapping ``{error_message: occurrence_count}`` for all ERROR entries.
    """
    summary: dict[str, int] = {}
    for entry in entries:
        if entry["type"] == "ERR":
            summary[entry["message"]] = summary.get(entry["message"], 0) + 1
    return summary


def compute_api_latency(entries: ParsedLog) -> dict[str, list[int]]:
    """
    Return a mapping ``{endpoint: [latency_ms, ...]}`` for all API call entries.
    """
    latency: dict[str, list[int]] = {}
    for entry in entries:
        if entry["type"] == "API":
            latency.setdefault(entry["endpoint"], []).append(entry["ms"])
    return latency


def compute_active_sessions(entries: ParsedLog) -> int:
    """
    Return the number of sessions that are currently open.

    A session is "active" when a ``logged in`` event has been seen for a user
    without a corresponding ``logged out`` event following it.
    """
    active: dict[str, str] = {}   # user_id → last_seen_timestamp
    for entry in entries:
        if entry["type"] == "USR":
            uid = entry["user_id"]
            action = entry["action"]
            if "logged in" in action:
                active[uid] = entry["timestamp"]
            elif "logged out" in action and uid in active:
                del active[uid]
    return len(active)


# ─────────────────────────────────────────────────────────────────────────────
# LOAD — write metrics to DB and render HTML report
# ─────────────────────────────────────────────────────────────────────────────

def init_database(path: str) -> sqlite3.Connection:
    """
    Create (or open) a SQLite database at *path* and return the connection.

    Creates two tables if they do not exist:
    - ``errors(dt, message, count)``
    - ``api_metrics(dt, endpoint, avg_ms)``
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def store_error_summary(conn: sqlite3.Connection, summary: dict[str, int]) -> None:
    """
    Persist *summary* (a ``{message: count}`` dict) into the ``errors`` table.

    Uses a parameterized query to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for msg, count in summary.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def store_api_metrics(conn: sqlite3.Connection, latency: dict[str, list[int]]) -> None:
    """
    Persist average latencies into the ``api_metrics`` table.

    Uses a parameterized query to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for endpoint, times in latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )
    conn.commit()


def render_html_report(
    error_summary: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Write the HTML report covering error summary, API latency table, and
    active session count to *output_path*.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_summary.items():
        # Escape HTML meta-characters to prevent content injection in the report.
        safe_msg = (
            err_msg.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
        )
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )

    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body></html>")

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline orchestration
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline:

    1. Read and parse ``LOG_FILE``.
    2. Compute error summary, API latency, and active session count.
    3. Persist metrics to the SQLite database at ``DB_PATH``.
    4. Write ``report.html`` with the same structure as the original.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # EXTRACT
    entries = parse_log_file(LOG_FILE)
    print(f"Extracted {len(entries)} log entries from {LOG_FILE}.")

    # TRANSFORM
    error_summary = compute_error_summary(entries)
    api_latency = compute_api_latency(entries)
    active_sessions = compute_active_sessions(entries)

    # LOAD – database
    conn = init_database(DB_PATH)
    store_error_summary(conn, error_summary)
    store_api_metrics(conn, api_latency)
    conn.close()

    # LOAD – report
    render_html_report(error_summary, api_latency, active_sessions, "report.html")

    print(f"Job finished at {datetime.datetime.now().isoformat()}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (with demo log generation when run directly)
# ─────────────────────────────────────────────────────────────────────────────

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
        with open(LOG_FILE, "w") as fh:
            fh.write(sample_log)
        print(f"Created sample {LOG_FILE}")

    run_pipeline()
