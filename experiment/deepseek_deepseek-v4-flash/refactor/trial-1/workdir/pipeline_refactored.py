"""Server log pipeline — extracts, transforms, and loads log data into a report.

Usage
-----
    export LOG_FILE=server.log      # default: server.log
    export DB_PATH=metrics.db        # default: metrics.db
    python pipeline_refactored.py

Output
------
    report.html — HTML report with error summary, API latency table,
                  and active session count.
"""

import datetime
import os
import re
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

LogEvent = dict[str, Any]
"""Parsed log line. Always has ``type`` and ``timestamp``; additional keys
depend on the event type (``message``, ``user_id``, ``action``, ``endpoint``,
``duration_ms``)."""

TransformResult = dict[str, Any]
"""Aggregated data ready for loading.

Keys
----
error_counts : dict[str, int]
    Error message text → occurrence count.
api_stats : dict[str, float]
    Endpoint path → average latency in milliseconds.
active_session_count : int
    Number of users currently logged in.
"""

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Pre-compiled regex patterns for each log line type, tried in order.
# Each pattern captures the ISO timestamp as group 1.
_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$"),
    re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\d+) logged in$"),
    re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\d+) logged out$"),
    re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"),
    re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.+)$"),
]


def extract_events(log_path: str) -> list[LogEvent]:
    """Parse a server log file and return structured event records.

    Lines that don't match any known pattern are silently skipped.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of parsed event dictionaries. Empty list when the file is
        missing or unreadable.
    """
    events: list[LogEvent] = []
    if not os.path.exists(log_path):
        return events

    with open(log_path, "r") as f:
        for line in f:
            event = _parse_line(line.rstrip("\n"))
            if event is not None:
                events.append(event)

    return events


def _parse_line(line: str) -> LogEvent | None:
    """Return a structured event dict for *line*, or *None* if unmatched."""
    # ERROR: timestamp ERROR message
    m = _PATTERNS[0].match(line)
    if m:
        return {"type": "ERR", "timestamp": m.group(1), "message": m.group(2)}

    # USER login: timestamp INFO User <id> logged in
    m = _PATTERNS[1].match(line)
    if m:
        return {
            "type": "USR",
            "timestamp": m.group(1),
            "user_id": m.group(2),
            "action": "logged in",
        }

    # USER logout: timestamp INFO User <id> logged out
    m = _PATTERNS[2].match(line)
    if m:
        return {
            "type": "USR",
            "timestamp": m.group(1),
            "user_id": m.group(2),
            "action": "logged out",
        }

    # API call: timestamp INFO API <endpoint> took <ms>ms
    m = _PATTERNS[3].match(line)
    if m:
        return {
            "type": "API",
            "timestamp": m.group(1),
            "endpoint": m.group(2),
            "duration_ms": int(m.group(3)),
        }

    # WARNING: timestamp WARN message
    m = _PATTERNS[4].match(line)
    if m:
        return {"type": "WARN", "timestamp": m.group(1), "message": m.group(2)}

    return None


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_events(events: list[LogEvent]) -> TransformResult:
    """Aggregate parsed events into error counts, API averages, and session state.

    Session tracking processes USR events in list order (login adds, logout
    removes). If a logout appears without a prior login, it is ignored.

    Args:
        events: Parsed event list from :func:`extract_events`.

    Returns:
        A dictionary with ``error_counts``, ``api_stats``, and
        ``active_session_count``.
    """
    error_counts: dict[str, int] = {}
    api_durations: dict[str, list[int]] = {}
    active_sessions: dict[str, str] = {}

    for ev in events:
        etype = ev["type"]

        if etype == "ERR":
            msg: str = ev["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif etype == "USR":
            uid: str = ev["user_id"]
            action: str = ev["action"]
            if action == "logged in":
                active_sessions[uid] = ev["timestamp"]
            elif action == "logged out" and uid in active_sessions:
                del active_sessions[uid]

        elif etype == "API":
            ep: str = ev["endpoint"]
            api_durations.setdefault(ep, []).append(ev["duration_ms"])

    api_stats: dict[str, float] = {
        ep: sum(durs) / len(durs) for ep, durs in api_durations.items()
    }

    return {
        "error_counts": error_counts,
        "api_stats": api_stats,
        "active_session_count": len(active_sessions),
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_sqlite(db_path: str, data: TransformResult) -> None:
    """Write aggregated data into the SQLite database.

    Creates ``errors`` and ``api_metrics`` tables if they don't exist. All
    inserts use parameterised queries (``?`` placeholders) to prevent SQL
    injection.

    Args:
        db_path: Path to the SQLite database file.
        data: Aggregated data from :func:`transform_events`.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

        for msg, count in data["error_counts"].items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg_ms in data["api_stats"].items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def _html_escape(text: str) -> str:
    """Replace ``&``, ``<``, ``>`` with their HTML entities."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_report(data: TransformResult, output_path: str) -> None:
    """Produce an HTML report file with error, latency, and session data.

    Args:
        data: Aggregated data from :func:`transform_events`.
        output_path: Destination path for the HTML file (e.g. ``report.html``).
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data["error_counts"].items():
        safe = _html_escape(err_msg)
        lines.append(f"<li><b>{safe}</b>: {count} occurrences</li>")

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for ep, avg_ms in data["api_stats"].items():
        lines.append(f"<tr><td>{ep}</td><td>{avg_ms:.1f}</td></tr>")

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{data['active_session_count']} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full pipeline: extract → transform → load (DB + HTML report)."""
    events = extract_events(LOG_FILE)
    data = transform_events(events)
    load_sqlite(DB_PATH, data)
    generate_report(data, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
