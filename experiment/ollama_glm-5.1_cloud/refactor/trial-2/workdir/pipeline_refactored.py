"""Server-log processing pipeline: Extract → Transform → Load.

Reads a server log file, parses structured entries (errors, user sessions,
API calls, warnings), persists aggregated metrics to SQLite, and generates
an HTML report.

All configuration is read from environment variables with sensible defaults:
  LOG_FILE   – path to the server log           (default: server.log)
  DB_PATH    – path to the SQLite database      (default: metrics.db)
  DB_HOST    – database host                     (default: localhost)
  DB_PORT    – database port                     (default: 5432)
  DB_USER    – database user                     (default: admin)
  DB_PASS    – database password                 (default: <empty>)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration – environment variables, no hardcoded secrets
# ---------------------------------------------------------------------------

LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "")

# ---------------------------------------------------------------------------
# Compiled regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# General log line: "2024-01-01 12:00:00 LEVEL ..."
_LOG_LINE_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>\S+)\s+(?P<rest>.*)"
)

# User action line: "User <uid> <action>"
_USER_RE = re.compile(r"User\s+(?P<uid>\S+)\s+(?P<action>.+)")

# API call line: "API <endpoint> took <duration>ms"
_API_RE = re.compile(r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """A parsed error log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A parsed user login/logout event."""

    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCall:
    """A parsed API call with latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarningEntry:
    """A parsed warning log entry."""

    timestamp: str
    message: str


@dataclass
class LogData:
    """Aggregation of all parsed log entries."""

    errors: list[ErrorEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract – parse raw log lines
# ---------------------------------------------------------------------------


def extract(log_path: str) -> LogData:
    """Read *log_path* and return structured :class:`LogData`.

    Lines that do not match the expected format are silently skipped.
    """
    data = LogData()
    path = Path(log_path)
    if not path.exists():
        return data

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                data.errors.append(ErrorEntry(timestamp=timestamp, message=rest))

            elif level == "WARN":
                data.warnings.append(WarningEntry(timestamp=timestamp, message=rest))

            elif level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    data.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            uid=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    data.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration")),
                        )
                    )


    return data


# ---------------------------------------------------------------------------
# Transform – compute derived aggregates
# ---------------------------------------------------------------------------


def _error_summary(errors: list[ErrorEntry]) -> dict[str, int]:
    """Return ``{message: count}`` for each distinct error."""
    summary: dict[str, int] = {}
    for entry in errors:
        summary[entry.message] = summary.get(entry.message, 0) + 1
    return summary


def _api_latency(api_calls: list[ApiCall]) -> dict[str, list[int]]:
    """Return ``{endpoint: [durations]}`` grouped by endpoint."""
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def _active_sessions(user_events: list[UserEvent]) -> dict[str, str]:
    """Return ``{uid: login_timestamp}`` for currently active sessions.

    A session is active when a login has been seen without a matching logout.
    """
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.uid] = event.timestamp
        elif "logged out" in event.action and event.uid in sessions:
            sessions.pop(event.uid)
    return sessions


# ---------------------------------------------------------------------------
# Load – persist to SQLite and generate report
# ---------------------------------------------------------------------------


def _load_to_db(
    db_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """Insert aggregated metrics into the SQLite database at *db_path*.

    Uses parameterized queries exclusively to prevent SQL injection.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    now = datetime.datetime.now().isoformat()

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in error_summary.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, durations in api_latency.items():
            avg_ms = sum(durations) / len(durations)
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()


def _generate_report(
    error_summary: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Write an HTML report to *output_path*.

    The report contains three sections matching the original script:
    error summary, API latency table, and active session count.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in error_summary.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, durations in api_latency.items():
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline.

    1. Extract log entries from the configured log file.
    2. Transform them into error summaries, API latency stats, and active sessions.
    3. Load aggregated metrics into SQLite and generate ``report.html``.
    """
    log_data = extract(LOG_FILE)

    error_summary = _error_summary(log_data.errors)
    api_latency = _api_latency(log_data.api_calls)
    active_sessions = _active_sessions(log_data.user_events)

    _load_to_db(DB_PATH, error_summary, api_latency)
    _generate_report(error_summary, api_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    run_pipeline()