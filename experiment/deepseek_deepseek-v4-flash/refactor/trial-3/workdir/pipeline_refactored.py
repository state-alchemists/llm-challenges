"""Refactored server-log analysis pipeline (extract -> transform -> load).

Reads all configuration from environment variables, parses ``server.log``
lines with regular expressions, aggregates error / API-latency / session
metrics, persists them to SQLite using parameterized queries, and renders
``report.html``.

Environment variables:
    LOG_FILE     — path to the server log (default: ``server.log``)
    DB_PATH      — path to the SQLite database (default: ``metrics.db``)
    REPORT_PATH  — path to write the HTML report (default: ``report.html``)
    DB_HOST, DB_PORT, DB_USER, DB_PASS — database connection settings,
        retained for a future remote backend. The SQLite loader does not
        use them, and they are never printed or logged.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    log_path: Path
    db_path: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables, with safe defaults."""
        return cls(
            log_path=Path(os.getenv("LOG_FILE", "server.log")),
            db_path=Path(os.getenv("DB_PATH", "metrics.db")),
            report_path=Path(os.getenv("REPORT_PATH", "report.html")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", ""),
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Timestamp is two space-separated tokens: YYYY-MM-DD HH:MM:SS
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) (?P<message>.+)$"
)
USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")


@dataclass(frozen=True)
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    kind: str  # "ERR" | "USR" | "API" | "WARN"
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


def extract_logs(log_path: Path) -> list[str]:
    """Read every line from the log file.

    Returns an empty list when the file does not exist so callers can
    still produce a report from an empty input.
    """
    if not log_path.exists():
        return []
    return log_path.read_text(encoding="utf-8").splitlines()


def parse_log_line(line: str) -> LogEntry | None:
    """Parse one log line into a LogEntry, or None if it is not recognizable.

    ERROR and WARN lines carry a free-form message. INFO lines are further
    classified as user events (login/logout) or API latency samples.
    """
    match = LOG_LINE_RE.match(line)
    if match is None:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message").strip()

    if level == "ERROR":
        return LogEntry(timestamp=timestamp, kind="ERR", message=message)
    if level == "WARN":
        return LogEntry(timestamp=timestamp, kind="WARN", message=message)

    # INFO: classify as a user event or an API sample.
    user_match = USER_RE.match(message)
    if user_match is not None:
        return LogEntry(
            timestamp=timestamp,
            kind="USR",
            user_id=user_match.group("user_id"),
            action=user_match.group("action"),
        )

    api_match = API_RE.match(message)
    if api_match is not None:
        duration = int(api_match.group("ms")) if api_match.group("ms") else 0
        return LogEntry(
            timestamp=timestamp,
            kind="API",
            endpoint=api_match.group("endpoint"),
            duration_ms=duration,
        )

    return None


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Metrics:
    """Aggregated metrics derived from parsed log entries."""

    error_counts: dict[str, int]
    endpoint_stats: dict[str, list[int]]
    active_session_count: int


def transform_entries(entries: list[LogEntry]) -> Metrics:
    """Aggregate log entries into error counts, API latency, and session count.

    Session tracking mirrors the original semantics: a "logged in" action
    registers the user; a "logged out" action removes them; the final count
    reflects users still active at the end of the log.
    """
    error_counts: dict[str, int] = {}
    endpoint_stats: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if entry.kind == "ERR" and entry.message is not None:
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.kind == "USR" and entry.user_id is not None:
            if entry.action is not None and "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif entry.action is not None and "logged out" in entry.action:
                sessions.pop(entry.user_id, None)
        elif entry.kind == "API" and entry.endpoint is not None:
            endpoint_stats.setdefault(entry.endpoint, []).append(
                entry.duration_ms if entry.duration_ms is not None else 0
            )

    return Metrics(
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        active_session_count=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_metrics(db_path: Path, metrics: Metrics) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Creates the ``errors`` and ``api_metrics`` tables when absent, then
    inserts one row per error message and per API endpoint with the
    computed average latency.
    """
    # ISO string matches the original "%s" formatting and avoids the
    # deprecated default datetime adapter (Python >= 3.12).
    now = datetime.datetime.now().isoformat(sep=" ")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        for message, count in metrics.error_counts.items():
            conn.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, times in metrics.endpoint_stats.items():
            avg_ms = sum(times) / len(times)
            conn.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )


def generate_report(report_path: Path, metrics: Metrics) -> None:
    """Render ``report.html`` with error summary, latency table, and
    active-session count.

    User-derived strings are HTML-escaped to prevent markup injection.
    """
    rows = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in metrics.error_counts.items():
        rows.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    rows += [
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for endpoint, times in metrics.endpoint_stats.items():
        avg_ms = sum(times) / len(times)
        rows.append(
            f"<tr><td>{html.escape(endpoint)}</td>"
            f"<td>{round(avg_ms, 1)}</td></tr>"
        )
    rows += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{metrics.active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    report_path.write_text("\n".join(rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


def write_sample_log(log_path: Path) -> None:
    """Create a sample server log when none exists, preserving original behavior."""
    log_path.write_text(SAMPLE_LOG, encoding="utf-8")


def main() -> None:
    """Run the extract -> transform -> load pipeline and render the report."""
    config = Config.from_env()

    if not config.log_path.exists():
        write_sample_log(config.log_path)

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    lines = extract_logs(config.log_path)
    entries = [
        parsed for parsed in (parse_log_line(line) for line in lines) if parsed is not None
    ]
    metrics = transform_entries(entries)

    load_metrics(config.db_path, metrics)
    generate_report(config.report_path, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
