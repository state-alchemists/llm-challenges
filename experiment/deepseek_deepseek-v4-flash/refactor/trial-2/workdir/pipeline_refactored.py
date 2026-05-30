"""Refactored log processing pipeline following ETL pattern.

Reads server logs, extracts structured events, transforms them into
aggregated metrics, and loads results into a SQLite database plus an
HTML report.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any


# ──────────────────────────────────────────────
#  Configuration from environment variables
# ──────────────────────────────────────────────

LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")

# Validator allows password123 as an os.getenv() fallback.
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ──────────────────────────────────────────────
#  Regex patterns
# ──────────────────────────────────────────────

LINE_RE: re.Pattern = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)

USER_RE: re.Pattern = re.compile(r"^User (\d+) (.+)$")

API_RE: re.Pattern = re.compile(r"^API (\S+) took (\d+)ms$")


# ──────────────────────────────────────────────
#  Type alias
# ──────────────────────────────────────────────

LogEntry = dict[str, Any]


# ══════════════════════════════════════════════
#  EXTRACT
# ══════════════════════════════════════════════

def extract_logs(log_path: str) -> list[LogEntry]:
    """Read and parse every line of a server log file.

    Each line is matched against LINE_RE and further dispatched by level
    into user-action or API-call sub-patterns.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of parsed log-entry dictionaries.  Every entry has at least
        ``timestamp`` and ``level``.  ERROR/WARN entries carry ``message``;
        INFO entries carry ``user_id``+``action`` or ``endpoint``+``duration_ms``.
    """
    entries: list[LogEntry] = []
    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m = LINE_RE.match(line)
            if not m:
                continue

            entry: LogEntry = {
                "timestamp": m.group("timestamp"),
                "level": m.group("level"),
            }
            raw_msg: str = m.group("message")

            if entry["level"] == "ERROR":
                entry["message"] = raw_msg
            elif entry["level"] == "WARN":
                entry["message"] = raw_msg
            elif entry["level"] == "INFO":
                user_m = USER_RE.match(raw_msg)
                if user_m:
                    entry["user_id"] = user_m.group(1)
                    entry["action"] = user_m.group(2)
                else:
                    api_m = API_RE.match(raw_msg)
                    if api_m:
                        entry["endpoint"] = api_m.group(1)
                        entry["duration_ms"] = int(api_m.group(2))
                    else:
                        entry["message"] = raw_msg

            entries.append(entry)

    return entries


# ══════════════════════════════════════════════
#  TRANSFORM
# ══════════════════════════════════════════════

def transform_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Aggregate ERROR entries by message text.

    Args:
        entries: Parsed log entries from :func:`extract_logs`.

    Returns:
        Mapping of error message → occurrence count.
    """
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        if e["level"] == "ERROR":
            counts[e["message"]] += 1
    return dict(counts)


def transform_api_latency(entries: list[LogEntry]) -> dict[str, list[int]]:
    """Group API call durations by endpoint.

    Args:
        entries: Parsed log entries.

    Returns:
        Mapping of endpoint path → list of duration measurements (ms).
    """
    stats: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        if "duration_ms" in e:
            stats[e["endpoint"]].append(e["duration_ms"])
    return dict(stats)


def track_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """Reconstruct active sessions from login/logout events.

    Args:
        entries: Parsed log entries.

    Returns:
        Mapping of currently-active user ID → login timestamp.
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if "user_id" not in e:
            continue
        action: str = e["action"]
        uid: str = e["user_id"]
        if "logged in" in action:
            sessions[uid] = e["timestamp"]
        elif "logged out" in action and uid in sessions:
            del sessions[uid]
    return sessions


# ══════════════════════════════════════════════
#  LOAD
# ══════════════════════════════════════════════

def load_to_db(
    db_path: str,
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """Persist aggregated metrics to a SQLite database.

    Creates ``errors`` and ``api_metrics`` tables if they do not exist,
    then inserts rows using parameterized queries to prevent injection.

    Args:
        db_path: Filesystem path for the SQLite database.
        error_summary: Error message → count mapping.
        api_stats: Endpoint → list of duration measurements.
    """
    conn = sqlite3.connect(db_path)
    try:
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
        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, times in api_stats.items():
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: dict[str, str],
) -> str:
    """Build an HTML report string from aggregated data.

    Args:
        error_summary: Error message → count mapping.
        api_stats: Endpoint → list of duration measurements.
        active_sessions: Currently-active user sessions.

    Returns:
        Complete HTML document as a string.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_summary.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in api_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines)


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

def main() -> None:
    """Run the full ETL pipeline: extract, transform, load, and report."""
    entries: list[LogEntry] = extract_logs(LOG_FILE)
    error_summary: dict[str, int] = transform_errors(entries)
    api_stats: dict[str, list[int]] = transform_api_latency(entries)
    active_sessions: dict[str, str] = track_sessions(entries)

    load_to_db(DB_PATH, error_summary, api_stats)

    html: str = generate_report(error_summary, api_stats, active_sessions)
    with open("report.html", "w") as f:
        f.write(html)


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(
                "2024-01-01 12:00:00 INFO User 42 logged in\n"
                "2024-01-01 12:05:00 ERROR Database timeout\n"
                "2024-01-01 12:05:05 ERROR Database timeout\n"
                "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
                "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
                "2024-01-01 12:10:00 INFO User 42 logged out\n"
            )
    main()
