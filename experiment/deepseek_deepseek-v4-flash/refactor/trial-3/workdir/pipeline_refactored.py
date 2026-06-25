"""Pipeline for processing server logs and generating system reports.

Follows Extract -> Transform -> Load pattern:
  - **Extract**: Parse log file into structured events
  - **Transform**: Aggregate errors, compute API latency, track sessions
  - **Load**: Write to SQLite database and produce HTML report

Usage:
    METRICS_DB_PATH=metrics.db LOG_FILE_PATH=server.log python pipeline_refactored.py
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


# ── Configuration (from environment variables) ───────────────────

DB_PATH: str = os.environ.get("METRICS_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE_PATH", "server.log")

# DB_HOST/PORT/USER/PASS are read from the environment for documentation
# purposes.  This pipeline uses SQLite, so these credentials are not
# consumed by the connection logic below.
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")


# ── Regex Patterns ───────────────────────────────────────────────

LINE_RE: re.Pattern[str] = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN|DEBUG) "
    r"(?P<body>.+)$"
)

USER_RE: re.Pattern[str] = re.compile(r"^User (\d+) (.+)$")

API_RE: re.Pattern[str] = re.compile(r"^API (\S+) took (\d+)ms$")


# ── Extract ──────────────────────────────────────────────────────


def parse_log_file(path: str | Path) -> list[dict[str, Any]]:
    """Read and parse every log line from *path* into structured events.

    Each returned dict has at least ``timestamp`` and ``type`` keys.
    Additional keys depend on the event type:

    - ``error`` / ``warn`` → ``message``
    - ``user``            → ``user_id``, ``action``
    - ``api``             → ``endpoint``, ``latency_ms``

    Unparseable lines are silently skipped.
    """
    log_path = Path(path)
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []

    with log_path.open("r") as f:
        for line in f:
            m = LINE_RE.match(line)
            if not m:
                continue

            ts = m.group("ts")
            level = m.group("level")
            body = m.group("body")

            if level == "ERROR":
                events.append(
                    {
                        "timestamp": ts,
                        "type": "error",
                        "message": body,
                    }
                )

            elif level == "WARN":
                events.append(
                    {
                        "timestamp": ts,
                        "type": "warn",
                        "message": body,
                    }
                )

            elif level == "INFO":
                user_m = USER_RE.match(body)
                api_m = API_RE.match(body)

                if user_m:
                    events.append(
                        {
                            "timestamp": ts,
                            "type": "user",
                            "user_id": user_m.group(1),
                            "action": user_m.group(2),
                        }
                    )
                elif api_m:
                    events.append(
                        {
                            "timestamp": ts,
                            "type": "api",
                            "endpoint": api_m.group(1),
                            "latency_ms": int(api_m.group(2)),
                        }
                    )

    return events


# ── Transform ────────────────────────────────────────────────────


def compute_error_summary(
    events: list[dict[str, Any]],
) -> dict[str, int]:
    """Count occurrences of each unique error message.

    Only events with ``type == "error"`` are considered.
    """
    summary: dict[str, int] = defaultdict(int)
    for ev in events:
        if ev.get("type") == "error":
            summary[ev["message"]] += 1
    return dict(summary)


def compute_api_latency(
    events: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute average latency in milliseconds per API endpoint.

    Only events with ``type == "api"`` are considered.
    Returns ``{endpoint: avg_ms}``.
    """
    totals: dict[str, list[int]] = defaultdict(list)
    for ev in events:
        if ev.get("type") == "api":
            totals[ev["endpoint"]].append(ev["latency_ms"])

    return {ep: sum(times) / len(times) for ep, times in totals.items()}


def count_active_sessions(events: list[dict[str, Any]]) -> int:
    """Replay user login/logout events to determine active session count.

    Only events with ``type == "user"`` are considered.  A user is
    considered logged in until a matching ``logged out`` action is seen.
    """
    sessions: dict[str, str] = {}
    for ev in events:
        if ev.get("type") != "user":
            continue
        uid = ev["user_id"]
        action = ev["action"]
        if "logged in" in action:
            sessions[uid] = ev["timestamp"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return len(sessions)


# ── Load ─────────────────────────────────────────────────────────


def load_to_db(
    db_path: str | Path,
    errors: dict[str, int],
    api_latencies: dict[str, float],
) -> None:
    """Write error summary and API latency metrics into the SQLite database.

    Uses **parameterized queries** to prevent SQL injection.
    Both tables (``errors``, ``api_metrics``) are created if they do not exist.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat()

        cur.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            [(now, msg, cnt) for msg, cnt in errors.items()],
        )
        cur.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            [(now, ep, avg) for ep, avg in api_latencies.items()],
        )

        conn.commit()
    finally:
        conn.close()


def generate_html(
    error_summary: dict[str, int],
    api_latencies: dict[str, float],
    active_session_count: int,
) -> str:
    """Build a self-contained HTML report string."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_summary.items():
        escaped = msg.replace("&", "&amp;").replace("<", "&lt;")
        lines.append(f"<li><b>{escaped}</b>: {count} occurrences</li>")

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for ep, avg in sorted(api_latencies.items()):
        escaped = ep.replace("&", "&amp;").replace("<", "&lt;")
        lines.append(f"<tr><td>{escaped}</td><td>{avg:.1f}</td></tr>")

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def write_report(html: str, output_path: str | Path = "report.html") -> None:
    """Write *html* to *output_path*."""
    Path(output_path).write_text(html, encoding="utf-8")


# ── Pipeline Orchestration ───────────────────────────────────────


def run_pipeline() -> None:
    """Execute the full Extract -> Transform -> Load pipeline."""
    print(f"Reading log file: {LOG_FILE}")

    events = parse_log_file(LOG_FILE)

    error_summary = compute_error_summary(events)
    api_latencies = compute_api_latency(events)
    active_sessions = count_active_sessions(events)

    print(f"Found {len(events)} events, {active_sessions} active session(s)")
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    load_to_db(DB_PATH, error_summary, api_latencies)
    html = generate_html(error_summary, api_latencies, active_sessions)
    write_report(html)

    print(f"Report written to report.html at {datetime.datetime.now()}")


# ── Bootstrap / Demo Data ────────────────────────────────────────


def _write_demo_log(path: str | Path) -> None:
    """Write a sample log file when none exists (development helper)."""
    demo = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    Path(path).write_text("\n".join(demo) + "\n", encoding="utf-8")
    print(f"Created demo log: {path}")


def main() -> None:
    """Entry point: create demo data if needed, then run the pipeline."""
    if not os.path.exists(LOG_FILE):
        _write_demo_log(LOG_FILE)
    run_pipeline()


if __name__ == "__main__":
    main()
