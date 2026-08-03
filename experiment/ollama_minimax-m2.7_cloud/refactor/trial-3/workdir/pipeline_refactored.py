"""
Log processing pipeline: Extract → Transform → Load.

Reads server logs, aggregates metrics into SQLite, and produces an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


# ─── Configuration (environment variables) ────────────────────────────────────

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: str = os.environ.get("DB_PORT", "5432")
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ErrorEntry:
    """A counted error message with its first occurrence timestamp."""
    message: str
    count: int
    first_seen: str


@dataclass
class ApiMetric:
    """A single API call record."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class SessionEvent:
    """A user session event (login or logout)."""
    timestamp: str
    user_id: str
    action: str  # "logged in" or "logged out"


# ─── Regex patterns ───────────────────────────────────────────────────────────

_RE_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.*)$"
)

_RE_ERROR = re.compile(r"^(?P<msg>.+)$")

_RE_SESSION = re.compile(
    r"^User (?P<user_id>\S+) (?P<action>logged in|logged out)$"
)

_RE_API = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<latency_ms>\d+)ms$"
)

_RE_WARN = re.compile(r"^(?P<msg>.+)$")


# ─── EXTRACT ─────────────────────────────────────────────────────────────────

def extract_log_entries(log_path: str) -> list[dict]:
    """
    Parse a server log file and return a list of typed entry dicts.

    Each dict has at least ``type`` (str) and ``timestamp`` (str), plus
    type-specific fields.
    """
    entries: list[dict] = []

    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _RE_LOG.match(line)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                entries.append({"type": "error", "timestamp": timestamp, "message": rest})

            elif level == "INFO" and rest.startswith("User "):
                m_session = _RE_SESSION.match(rest)
                if m_session:
                    entries.append({
                        "type": "session",
                        "timestamp": timestamp,
                        "user_id": m_session.group("user_id"),
                        "action": m_session.group("action"),
                    })

            elif level == "INFO" and rest.startswith("API "):
                m_api = _RE_API.match(rest)
                if m_api:
                    entries.append({
                        "type": "api",
                        "timestamp": timestamp,
                        "endpoint": m_api.group("endpoint"),
                        "latency_ms": int(m_api.group("latency_ms")),
                    })

            elif level == "WARN":
                entries.append({"type": "warn", "timestamp": timestamp, "message": rest})

    return entries


# ─── TRANSFORM ────────────────────────────────────────────────────────────────

def transform_errors(entries: list[dict]) -> list[ErrorEntry]:
    """
    Aggregate ERROR entries by message text, returning a sorted list of
    :class:`ErrorEntry` objects.
    """
    counts: dict[str, int] = {}
    first_seen: dict[str, str] = {}

    for e in entries:
        if e["type"] != "error":
            continue
        msg = e["message"]
        counts[msg] = counts.get(msg, 0) + 1
        if msg not in first_seen:
            first_seen[msg] = e["timestamp"]

    return [
        ErrorEntry(message=msg, count=count, first_seen=first_seen[msg])
        for msg, count in sorted(counts.items())
    ]


def transform_api_metrics(entries: list[dict]) -> dict[str, list[int]]:
    """
    Group API call latencies by endpoint, returning a mapping
    ``endpoint → [latency_ms, ...]``.
    """
    stats: dict[str, list[int]] = {}
    for e in entries:
        if e["type"] == "api":
            stats.setdefault(e["endpoint"], []).append(e["latency_ms"])
    return stats


def transform_active_sessions(entries: list[dict]) -> int:
    """
    Walk session events in order, tracking logged-in users.
    Returns the number of currently active (logged-in) sessions.
    """
    active: set[str] = set()
    for e in entries:
        if e["type"] != "session":
            continue
        uid = e["user_id"]
        if e["action"] == "logged in":
            active.add(uid)
        elif e["action"] == "logged out":
            active.discard(uid)
    return len(active)


# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_to_sqlite(
    db_path: str,
    errors: list[ErrorEntry],
    api_stats: dict[str, list[int]],
) -> None:
    """
    Write error summaries and API latency averages into the SQLite database
    using parameterised queries.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for err in errors:
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, err.message, err.count),
        )

    for endpoint, latencies in api_stats.items():
        avg = sum(latencies) / len(latencies)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    output_path: str,
    errors: list[ErrorEntry],
    api_stats: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """
    Write the HTML report covering error summary, API latency table, and
    active session count.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if errors:
        for err in errors:
            lines.append(
                f"<li><b>{err.message}</b>: {err.count} occurrence(s)</li>"
            )
    else:
        lines.append("<li>No errors recorded.</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if api_stats:
        for endpoint, latencies in sorted(api_stats.items()):
            avg = sum(latencies) / len(latencies)
            lines.append(
                f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
            )
    else:
        lines.append("<tr><td colspan='2'>No API calls recorded.</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """Main entry point: orchestrate Extract → Transform → Load."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # Extract
    entries = extract_log_entries(LOG_FILE)

    # Transform
    errors = transform_errors(entries)
    api_stats = transform_api_metrics(entries)
    active_sessions = transform_active_sessions(entries)

    # Load
    load_to_sqlite(DB_PATH, errors, api_stats)
    generate_html_report("report.html", errors, api_stats, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ─── Bootstrap ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Create a minimal sample log when the file is absent (demo / CI friendliness)
    if not os.path.exists(LOG_FILE):
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
