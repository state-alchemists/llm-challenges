"""Refactored pipeline — processes server logs and generates a system report.

Reads server logs via regex-based extraction, aggregates errors, API latency,
and active sessions, then writes results to a SQLite database and an HTML
report. All config comes from environment variables.
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


def load_config() -> dict[str, str]:
    """Read pipeline configuration from environment variables.

    Returns a dict with keys: log_file, db_path, db_host, db_port, db_user, db_pass.
    Every key has a sensible default so the script works out of the box.
    """
    return {
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)

_USER_PATTERN = re.compile(r"^User (\d+) (.+)$")
_API_PATTERN = re.compile(r"^API (\S+)(?: took (\d+)ms)?$")


def extract_logs(log_path: str) -> list[dict[str, Any]]:
    """Parse a server log file into structured entry dicts.

    Each returned dict contains ``timestamp`` (str), ``level`` (str),
    ``message`` (str), and type-specific fields:
    - ERROR / WARN: ``message`` only.
    - INFO (User): ``user_id`` (str), ``action`` (str).
    - INFO (API): ``endpoint`` (str), ``latency_ms`` (int or None).

    Lines that don't match the expected format are silently skipped.
    """
    entries: list[dict[str, Any]] = []

    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _LOG_PATTERN.match(line)
            if not match:
                continue

            entry: dict[str, Any] = {
                "timestamp": match.group("timestamp"),
                "level": match.group("level"),
                "message": match.group("message"),
            }

            level = entry["level"]
            msg = entry["message"]

            if level == "ERROR":
                entry["type"] = "ERR"
            elif level == "WARN":
                entry["type"] = "WARN"
            elif level == "INFO":
                user_match = _USER_PATTERN.match(msg)
                if user_match:
                    entry["type"] = "USR"
                    entry["user_id"] = user_match.group(1)
                    entry["action"] = user_match.group(2)
                else:
                    api_match = _API_PATTERN.match(msg)
                    if api_match:
                        entry["type"] = "API"
                        entry["endpoint"] = api_match.group(1)
                        raw_latency = api_match.group(2)
                        entry["latency_ms"] = int(raw_latency) if raw_latency else None

            entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_errors(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each error message.

    Only entries with ``type == "ERR"`` are included.
    Returns a mapping of error message → count.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.get("type") == "ERR":
            msg = entry["message"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def transform_api_latency(
    entries: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute average latency per API endpoint.

    Only entries with ``type == "API"`` and a numeric ``latency_ms`` are
    included. Returns a mapping of endpoint → average milliseconds (float).
    """
    raw: dict[str, list[int]] = {}
    for entry in entries:
        if entry.get("type") == "API" and entry.get("latency_ms") is not None:
            ep: str = entry["endpoint"]
            raw.setdefault(ep, []).append(entry["latency_ms"])

    averages: dict[str, float] = {}
    for ep, times in raw.items():
        averages[ep] = sum(times) / len(times)
    return averages


def transform_sessions(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Track currently active user sessions from login/logout events.

    A session starts when a user performs "logged in" and ends on
    "logged out". Returns a dict of user_id → session start timestamp
    for users still active.
    """
    sessions: dict[str, str] = {}
    for entry in entries:
        if entry.get("type") != "USR":
            continue
        uid: str = entry["user_id"]
        action: str = entry["action"]
        if "logged in" in action:
            sessions[uid] = entry["timestamp"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_database(
    db_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, float],
) -> None:
    """Write aggregated error and API metrics into a SQLite database.

    Creates ``errors`` and ``api_metrics`` tables if they don't exist, then
    inserts one row per error message and one row per API endpoint. Uses
    parameterized queries to prevent SQL injection.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()
    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in api_stats.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def load_report(
    output_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    sessions: dict[str, str],
) -> None:
    """Generate an HTML system report with error summary, API latency table,
    and active session count.

    All HTML content is generated inline without external templates so
    the report is self-contained.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        lines.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>"
        )
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in api_stats.items():
        lines.append(
            f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(
        f"<p>{len(sessions)} user(s) currently active</p>"
    )
    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full pipeline: extract → transform → load.

    1. Reads config from environment variables.
    2. Parses the server log.
    3. Aggregates errors, API latency, and active sessions.
    4. Writes results to a SQLite database and an HTML report.
    """
    config = load_config()
    log_path: str = config["log_file"]
    db_path: str = config["db_path"]

    print(f"Parsing {log_path}...")
    entries = extract_logs(log_path)

    print("Transforming data...")
    error_counts = transform_errors(entries)
    api_stats = transform_api_latency(entries)
    sessions = transform_sessions(entries)

    print("Loading into database...")
    load_database(db_path, error_counts, api_stats)

    print("Generating report...")
    load_report("report.html", error_counts, api_stats, sessions)

    print(f"Report written to report.html")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_FIXTURE_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


if __name__ == "__main__":
    config = load_config()
    if not os.path.exists(config["log_file"]):
        with open(config["log_file"], "w") as f:
            for line in _FIXTURE_LINES:
                f.write(line + "\n")
    main()
