#!/usr/bin/env python3
"""
Pipeline: Parse server logs → store metrics in SQLite → emit HTML report.

Architecture follows an Extract → Transform → Load (ETL) pattern.
Configuration is driven entirely by environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import TypedDict

# ---------------------------------------------------------------------------
# Config — read from environment with safe defaults for local development
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: str = os.environ.get("DB_PORT", "5432")
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")  # never hardcode; leave empty in dev


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ErrorEntry(TypedDict):
    dt: str
    t: str
    m: str


class SessionEntry(TypedDict):
    dt: str
    t: str
    u: str
    a: str


class ApiCallEntry(TypedDict):
    dt: str
    endpoint: str
    ms: int


class ParsedLog(TypedDict):
    errors: list[ErrorEntry]
    sessions: dict[str, str]  # uid -> login_dt
    api_calls: list[ApiCallEntry]


# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level, compiled once)
# ---------------------------------------------------------------------------

_RE_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN)"
    r"(?:\s(?P<rest>.*))?$"
)

_RE_USER = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>logged in|logged out|.*)$"
)

_RE_API = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT — parse raw log lines into structured records
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: str) -> ParsedLog:
    """
    Read *log_path* and return a structured dict of errors, sessions,
    and API calls.

    Returns
    -------
    ParsedLog
        ``{"errors": [...], "sessions": {uid: dt}, "api_calls": [...]}``
    """
    errors: list[ErrorEntry] = []
    sessions: dict[str, str] = {}
    api_calls: list[ApiCallEntry] = []

    if not os.path.exists(log_path):
        print(f"[WARN] Log file not found: {log_path}")
        return {"errors": errors, "sessions": sessions, "api_calls": api_calls}

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _RE_LOG.match(line)
            if not m:
                continue

            dt = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest") or ""

            if level == "ERROR":
                errors.append(ErrorEntry(dt=dt, t="ERR", m=rest))

            elif level == "INFO":
                user_m = _RE_USER.match(rest)
                if user_m:
                    uid = user_m.group("uid")
                    action = user_m.group("action")
                    if action == "logged in":
                        sessions[uid] = dt
                    elif action == "logged out" and uid in sessions:
                        sessions.pop(uid)
                    # passive session events (login/logout) are tracked but
                    # not surfaced as separate log entries in the report
                    continue

                api_m = _RE_API.match(rest)
                if api_m:
                    api_calls.append(ApiCallEntry(
                        dt=dt,
                        endpoint=api_m.group("endpoint"),
                        ms=int(api_m.group("ms")),
                    ))

            elif level == "WARN":
                errors.append(ErrorEntry(dt=dt, t="WARN", m=rest))

    return {"errors": errors, "sessions": sessions, "api_calls": api_calls}


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate raw records into report-ready summaries
# ---------------------------------------------------------------------------

def transform_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """
    Count occurrences of each distinct error message.

    Returns
    -------
    dict[str, int]
        ``{message: count}``
    """
    counts: dict[str, int] = {}
    for e in errors:
        if e["t"] == "ERR":          # WARN entries are informational only
            counts[e["m"]] = counts.get(e["m"], 0) + 1
    return counts


def transform_api_metrics(
    api_calls: list[ApiCallEntry],
) -> dict[str, float]:
    """
    Compute average latency per endpoint.

    Returns
    -------
    dict[str, float]
        ``{endpoint: avg_ms}``
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call["endpoint"], []).append(call["ms"])

    return {ep: sum(times) / len(times) for ep, times in stats.items()}


# ---------------------------------------------------------------------------
# LOAD — write summaries to SQLite and emit the HTML report
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, float],
    db_host: str,
    db_port: str,
    db_user: str,
) -> None:
    """
    Create (or open) *db_path* and persist *error_counts* and *api_metrics*
    using **parameterized queries** — no string formatting.

    Parameters
    ----------
    db_path
        SQLite file path.
    error_counts
        ``{message: count}``.
    api_metrics
        ``{endpoint: avg_ms}``.
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    # Safe, parameterized inserts — prevents SQL injection
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_metrics.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()
    print(f"Metrics written to {db_path}.")


def generate_html_report(
    error_counts: dict[str, int],
    api_metrics: dict[str, float],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """
    Write ``output_path`` as a self-contained HTML report.

    Parameters
    ----------
    error_counts
        ``{message: count}`` for the Error Summary section.
    api_metrics
        ``{endpoint: avg_ms}`` for the API Latency table.
    active_sessions
        Current number of active (logged-in) sessions.
    output_path
        Destination file path.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"<title>System Report — {now}</title>",
        "</head>",
        "<body>",
        f"<p><em>Generated {now}</em></p>",
        "",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if error_counts:
        for msg, count in error_counts.items():
            # Escape HTML metacharacters in user content
            safe_msg = (
                msg.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
            )
            lines.append(f"<li><b>{safe_msg}</b>: {count} occurrence(s)</li>")
    else:
        lines.append("<li><i>No errors recorded.</i></li>")

    lines.extend([
        "</ul>",
        "",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if api_metrics:
        for endpoint, avg_ms in sorted(api_metrics.items()):
            safe_ep = (
                endpoint.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
            )
            lines.append(
                f"<tr><td>{safe_ep}</td>"
                f"<td>{round(avg_ms, 1):.1f}</td></tr>"
            )
    else:
        lines.append("<tr><td colspan='2'><i>No API calls recorded.</i></td></tr>")

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

    print(f"Report written to {output_path}.")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Top-level entry point: orchestrate the full ETL pipeline."""
    print(f"Starting pipeline at {datetime.datetime.now()}...")

    # EXTRACT
    parsed = extract_log_entries(LOG_FILE)

    # TRANSFORM
    error_counts = transform_errors(parsed["errors"])
    api_metrics = transform_api_metrics(parsed["api_calls"])
    active_sessions = len(parsed["sessions"])

    # LOAD
    load_to_db(
        DB_PATH, error_counts, api_metrics,
        DB_HOST, DB_PORT, DB_USER,
    )
    generate_html_report(error_counts, api_metrics, active_sessions)

    print(f"Pipeline finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap — create a minimal sample log when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        print(f"[INFO] {LOG_FILE} not found; creating sample log.")
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as fh:
            fh.write("\n".join(sample_lines) + "\n")

    run_pipeline()
