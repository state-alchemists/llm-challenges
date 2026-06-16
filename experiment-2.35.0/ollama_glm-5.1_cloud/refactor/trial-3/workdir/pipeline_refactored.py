"""Server-log ETL pipeline: extract from log file, transform, load into SQLite, and generate an HTML report.

All configuration is read from environment variables with sensible defaults.
Uses parameterized SQL queries and regex-based log parsing.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from html import escape

# ---------------------------------------------------------------------------
# Configuration — all driven by environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("METRICS_DB_PATH", "metrics.db")
LOG_FILE_PATH: str = os.getenv("LOG_FILE_PATH", "server.log")
REPORT_PATH: str = os.getenv("REPORT_PATH", "report.html")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A parsed INFO User log line (login / logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A parsed INFO API log line with latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class WarningEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all parsed log entries."""

    errors: list[ErrorEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.+)$")
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\S+) (?P<action>.+)$"
)
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+)(?: took (?P<latency>\d+)ms)?$"
)
_RE_WARN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.+)$")


# ---------------------------------------------------------------------------
# Extract — read and parse the log file
# ---------------------------------------------------------------------------


def parse_log_file(log_path: Path) -> ParsedLog:
    """Read *log_path* and return structured :class:`ParsedLog`.

    Each line is matched against compiled regex patterns for ERROR, User,
    API, and WARN entries. Unrecognised lines are silently skipped.
    """
    result = ParsedLog()

    if not log_path.exists():
        return result

    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue

            if (m := _RE_ERROR.match(line)):
                result.errors.append(ErrorEntry(m["timestamp"], m["message"]))
            elif (m := _RE_USER.match(line)):
                result.user_events.append(
                    UserEvent(m["timestamp"], m["user_id"], m["action"])
                )
            elif (m := _RE_API.match(line)):
                latency = int(m["latency"]) if m["latency"] else 0
                result.api_calls.append(ApiCall(m["timestamp"], m["endpoint"], latency))
            elif (m := _RE_WARN.match(line)):
                result.warnings.append(WarningEntry(m["timestamp"], m["message"]))

    return result


# ---------------------------------------------------------------------------
# Transform — aggregate parsed data
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Return a mapping of error message → occurrence count."""
    counts: dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def aggregate_api_metrics(api_calls: list[ApiCall]) -> dict[str, list[int]]:
    """Return a mapping of endpoint → list of latency values."""
    metrics: dict[str, list[int]] = {}
    for call in api_calls:
        metrics.setdefault(call.endpoint, []).append(call.latency_ms)
    return metrics


def compute_active_sessions(user_events: list[UserEvent]) -> int:
    """Return the number of users still logged in after processing all events."""
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return len(sessions)


# ---------------------------------------------------------------------------
# Load — write to SQLite and generate the HTML report
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
) -> None:
    """Insert aggregated error and API-metric data into *db_path* using parameterized queries."""
    now = str(datetime.datetime.now())
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in error_counts.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, latencies in api_metrics.items():
            avg = sum(latencies) / len(latencies)
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """Write an HTML report to *output_path* with error summary, API latency table, and active session count."""
    parts: list[str] = []

    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")
    parts.append("<h1>Error Summary</h1>")
    parts.append("<ul>")
    for err_msg, count in error_counts.items():
        parts.append(f"<li><b>{escape(err_msg)}</b>: {count} occurrences</li>")
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, latencies in api_metrics.items():
        avg = round(sum(latencies) / len(latencies), 1)
        parts.append(f"<tr><td>{escape(endpoint)}</td><td>{avg}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{active_sessions} user(s) currently active</p>")
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full ETL pipeline: extract → transform → load → report."""
    log_path = Path(LOG_FILE_PATH)

    # --- Extract ---
    parsed = parse_log_file(log_path)

    # --- Transform ---
    error_counts = aggregate_errors(parsed.errors)
    api_metrics = aggregate_api_metrics(parsed.api_calls)
    active_sessions = compute_active_sessions(parsed.user_events)

    # --- Load ---
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    load_to_database(DB_PATH, error_counts, api_metrics)
    generate_report(error_counts, api_metrics, active_sessions, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log = Path(LOG_FILE_PATH)
    if not log.exists():
        with log.open("w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()