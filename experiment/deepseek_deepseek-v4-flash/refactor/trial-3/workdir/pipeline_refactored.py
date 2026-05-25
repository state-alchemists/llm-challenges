"""
Pipeline: extract, transform, and load server logs into a system report.

Supports four log levels and three INFO subtypes:
    - ERROR <message>
    - WARN <message>
    - INFO User <id> logged in / out
    - INFO API <endpoint> took <duration>ms

Configuration is read from environment variables (see load_config).
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Read pipeline configuration from environment variables with defaults."""
    return {
        "log_file": os.environ.get("LOG_FILE_PATH", "server.log"),
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": int(os.environ.get("DB_PORT", "5432")),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_BASE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR|INFO|WARN) (.*)$")
_USER_RE = re.compile(r"^User (\d+) (logged in|logged out)")
_API_RE = re.compile(r"^API (\S+) took (\d+)ms")


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a single log line into a structured dict, or *None* if unparseable."""
    m = _BASE_RE.match(line.strip())
    if not m:
        return None

    timestamp, level, body = m.group(1), m.group(2), m.group(3)
    entry: dict[str, Any] = {"timestamp": timestamp, "level": level}

    if level == "ERROR":
        entry["type"] = "error"
        entry["message"] = body

    elif level == "WARN":
        entry["type"] = "warn"
        entry["message"] = body

    elif level == "INFO":
        user_m = _USER_RE.match(body)
        api_m = _API_RE.match(body)

        if user_m:
            entry["type"] = "user_action"
            entry["user_id"] = user_m.group(1)
            entry["action"] = user_m.group(2)

        elif api_m:
            entry["type"] = "api_call"
            entry["endpoint"] = api_m.group(1)
            entry["duration_ms"] = int(api_m.group(2))

        else:
            # Unrecognised INFO — still record it
            entry["type"] = "info"
            entry["message"] = body

    return entry


def read_logs(file_path: str) -> list[dict[str, Any]]:
    """Read and parse every line in the log file.

    Returns an ordered list of parsed entries; unparseable lines are skipped.
    """
    if not os.path.exists(file_path):
        return []

    entries: list[dict[str, Any]] = []
    with open(file_path, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def compute_error_summary(logs: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    summary: dict[str, int] = {}
    for entry in logs:
        if entry.get("type") == "error":
            msg = entry["message"]
            summary[msg] = summary.get(msg, 0) + 1
    return summary


def compute_api_latency(logs: list[dict[str, Any]]) -> dict[str, float]:
    """Compute the average latency (ms) per API endpoint.

    Returns a mapping of endpoint -> average duration in milliseconds.
    """
    times: dict[str, list[int]] = {}
    for entry in logs:
        if entry.get("type") == "api_call":
            ep = entry["endpoint"]
            times.setdefault(ep, []).append(entry["duration_ms"])

    avg_latency: dict[str, float] = {}
    for ep, durations in times.items():
        avg_latency[ep] = sum(durations) / len(durations)
    return avg_latency


def compute_active_session_count(logs: list[dict[str, Any]]) -> int:
    """Simulate user sessions and return the count of currently active users.

    Processes user_action entries in chronological log order.
    """
    sessions: dict[str, str] = {}
    for entry in logs:
        if entry.get("type") != "user_action":
            continue
        uid = entry["user_id"]
        action = entry["action"]
        if action == "logged in":
            sessions[uid] = entry["timestamp"]
        elif action == "logged out" and uid in sessions:
            del sessions[uid]
    return len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def save_to_database(
    db_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Persist error summary and API latency into the database.

    Queries are parameterised to prevent SQL injection.
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

        now = datetime.datetime.now().isoformat()
        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg in api_latency.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, round(avg, 1)),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_count: int,
) -> str:
    """Build a standalone HTML report from the computed metrics."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_summary.items():
        lines.append(
            f"<li><b>{_html_escape(err_msg)}</b>: "
            f"{count} occurrence{'s' if count != 1 else ''}</li>"
        )
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])

    if api_latency:
        lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
        for ep, avg in sorted(api_latency.items()):
            lines.append(
                f"<tr><td>{_html_escape(ep)}</td><td>{avg:.1f}</td></tr>"
            )
    lines.append("</table>")

    lines.extend([
        "<h2>Active Sessions</h2>",
        f"<p>{active_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines) + "\n"


def _html_escape(text: str) -> str:
    """Minimal HTML-escaping for safe inclusion in rendered output."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full pipeline: extract logs, transform metrics, load results."""
    config = load_config()

    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    logs = read_logs(config["log_file"])
    error_summary = compute_error_summary(logs)
    api_latency = compute_api_latency(logs)
    active_count = compute_active_session_count(logs)

    save_to_database(config["db_path"], error_summary, api_latency)

    html = generate_report(error_summary, api_latency, active_count)
    report_path = "report.html"
    with open(report_path, "w") as f:
        f.write(html)

    print(f"Report written to {report_path}")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE_DATA = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )

    cfg = load_config()
    if not os.path.exists(cfg["log_file"]):
        with open(cfg["log_file"], "w") as f:
            f.write(SAMPLE_DATA)

    main()
