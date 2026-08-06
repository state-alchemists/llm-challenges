"""Server-log reporting pipeline (refactored).

Reads all configuration from environment variables, parses ``server.log``
into structured records (Extract), aggregates errors, API latencies and
active sessions (Transform), then persists the results to SQLite and writes
``report.html`` (Load).

Environment variables:
    DB_PATH  — SQLite database file (default: metrics.db)
    LOG_FILE — server log to process (default: server.log)
    DB_HOST  — database host, shown in the connection banner (default: localhost)
    DB_PORT  — database port, shown in the connection banner (default: 5432)
    DB_USER  — database user, shown in the connection banner (default: admin)
    DB_PASS  — database password, accepted for config parity; the SQLite
               backend does not authenticate (default: "")

Run from the directory that contains the log file:

    python pipeline_refactored.py
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — every value is overridable via environment variables.
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "")

# ---------------------------------------------------------------------------
# Log parsing (regex)
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO|DEBUG) (?P<body>.+)$"
)
_USER_ACTION_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")


@dataclass
class LogEntry:
    """A single parsed line from the server log."""

    timestamp: str
    level: str
    message: str = ""
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: Path) -> list[LogEntry]:
    """Parse ``log_path`` into structured log entries.

    Lines that do not match the expected format are skipped. ERROR/WARN
    bodies become ``message``; INFO lines become either a user action
    (``user_id`` + ``action``) or an API call (``endpoint`` + ``duration_ms``).
    """
    entries: list[LogEntry] = []
    with log_path.open("r", encoding="utf-8") as log_file:
        for raw_line in log_file:
            line = raw_line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if match is None:
                continue
            entry = LogEntry(
                timestamp=match.group("timestamp"),
                level=match.group("level"),
            )
            body = match.group("body")
            if entry.level in ("ERROR", "WARN"):
                entry.message = body
            elif entry.level == "INFO":
                user_match = _USER_ACTION_RE.match(body)
                if user_match is not None:
                    entry.user_id = user_match.group("user_id")
                    entry.action = user_match.group("action")
                else:
                    api_match = _API_CALL_RE.match(body)
                    if api_match is not None:
                        entry.endpoint = api_match.group("endpoint")
                        duration = api_match.group("duration")
                        entry.duration_ms = int(duration) if duration else 0
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_log_entries(
    entries: list[LogEntry],
) -> tuple[dict[str, int], dict[str, float], dict[str, str]]:
    """Aggregate log entries into report-ready statistics.

    Returns ``(error_counts, endpoint_stats, sessions)`` where
    ``error_counts`` maps each distinct error message to its occurrence
    count, ``endpoint_stats`` maps each API endpoint to its average latency
    in milliseconds, and ``sessions`` maps currently active user IDs to the
    timestamp of their most recent login.
    """
    error_counts: dict[str, int] = {}
    endpoint_times: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.user_id is not None and entry.action is not None:
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                del sessions[entry.user_id]
        elif entry.endpoint is not None:
            endpoint_times.setdefault(entry.endpoint, []).append(entry.duration_ms)

    endpoint_stats: dict[str, float] = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }
    return error_counts, endpoint_stats, sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_results(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, float],
    sessions: dict[str, str],
    db_path: Path,
    report_path: Path,
) -> None:
    """Persist the aggregates to SQLite and write the HTML report.

    All SQL statements use ``?`` placeholders with bound parameters to
    avoid string-interpolation injection. ``report_path`` receives the
    rendered report generated by :func:`render_report`.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now = str(datetime.now())
        for message, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, average in endpoint_stats.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, average),
            )
        conn.commit()
    finally:
        conn.close()

    report_path.write_text(
        render_report(error_counts, endpoint_stats, sessions),
        encoding="utf-8",
    )


def render_report(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, float],
    sessions: dict[str, str],
) -> str:
    """Render the HTML report: error summary, latency table, session count."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in error_counts.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, average in endpoint_stats.items():
        lines.append(
            f"<tr><td>{html.escape(endpoint)}</td>"
            f"<td>{round(average, 1)}</td></tr>"
        )
    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _write_demo_log(log_path: Path) -> None:
    """Create a small sample log so the pipeline runs on a fresh checkout."""
    log_path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
        encoding="utf-8",
    )


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        _write_demo_log(log_path)
    entries = extract_log_entries(log_path)
    error_counts, endpoint_stats, sessions = transform_log_entries(entries)
    load_results(error_counts, endpoint_stats, sessions, Path(DB_PATH), Path("report.html"))
    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    main()
