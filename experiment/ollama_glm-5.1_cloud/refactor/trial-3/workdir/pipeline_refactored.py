"""Pipeline for processing server logs and generating reports.

Extracts log entries, transforms them into aggregated metrics,
loads results into a SQLite database, and generates an HTML report.

Configuration is sourced entirely from environment variables:
  DB_PATH, LOG_FILE, DB_HOST, DB_PORT, DB_USER, DB_PASS, REPORT_PATH
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration – all values sourced from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")
REPORT_PATH: str = os.environ.get("REPORT_PATH", "report.html")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<rest>.+)$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<latency>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A log line at ERROR level."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A log line describing a user action (login / logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A log line describing an API call with optional latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """A log line at WARN level."""

    timestamp: str
    message: str


LogEntry = ErrorEntry | UserEvent | ApiCall | WarnEntry


# ---------------------------------------------------------------------------
# Aggregated results
# ---------------------------------------------------------------------------


@dataclass
class ErrorSummary:
    """Count of occurrences per unique error message."""

    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ApiLatency:
    """Average latency (ms) per API endpoint."""

    averages: dict[str, float] = field(default_factory=dict)


@dataclass
class SessionTracker:
    """Tracks currently active user sessions."""

    active_count: int = 0


@dataclass
class TransformResult:
    """Output of the transform phase."""

    error_summary: ErrorSummary = field(default_factory=ErrorSummary)
    api_latency: ApiLatency = field(default_factory=ApiLatency)
    sessions: SessionTracker = field(default_factory=SessionTracker)


# ---------------------------------------------------------------------------
# Extract – read and parse log lines
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a structured entry.

    Returns ``None`` if the line does not match the expected format.
    """
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    rest = match.group("rest")

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, message=rest)

    if level == "WARN":
        return WarnEntry(timestamp=timestamp, message=rest)

    if level == "INFO":
        user_match = _USER_RE.match(rest)
        if user_match is not None:
            return UserEvent(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )

        api_match = _API_RE.match(rest)
        if api_match is not None:
            latency = int(api_match.group("latency") or "0")
            return ApiCall(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                latency_ms=latency,
            )

    return None


def extract(log_path: str) -> list[LogEntry]:
    """Read the log file and return a list of parsed entries.

    Lines that do not match the expected format are silently skipped.
    """
    entries: list[LogEntry] = []
    path = Path(log_path)
    if not path.exists():
        return entries

    with path.open() as f:
        for line in f:
            entry = parse_log_line(line.rstrip("\n"))
            if entry is not None:
                entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Transform – aggregate entries into metrics
# ---------------------------------------------------------------------------


def transform(entries: list[LogEntry]) -> TransformResult:
    """Aggregate parsed log entries into error counts, API latency stats,
    and active session count.
    """
    error_counts: dict[str, int] = {}
    latency_by_endpoint: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, UserEvent):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)

        elif isinstance(entry, ApiCall):
            latency_by_endpoint.setdefault(entry.endpoint, []).append(
                entry.latency_ms
            )

    api_averages = {
        ep: sum(times) / len(times)
        for ep, times in latency_by_endpoint.items()
    }

    return TransformResult(
        error_summary=ErrorSummary(counts=error_counts),
        api_latency=ApiLatency(averages=api_averages),
        sessions=SessionTracker(active_count=len(sessions)),
    )


# ---------------------------------------------------------------------------
# Load – persist to database and generate report
# ---------------------------------------------------------------------------


def load_db(result: TransformResult, db_path: str) -> None:
    """Persist aggregated metrics into the SQLite database.

    Uses parameterized queries to prevent SQL injection.
    """
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

        for msg, count in result.error_summary.counts.items():
            cur.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for endpoint, avg in result.api_latency.averages.items():
            cur.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)", (now, endpoint, avg)
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(result: TransformResult) -> str:
    """Build the HTML report string from aggregated metrics."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in result.error_summary.counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, avg in result.api_latency.averages.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{result.sessions.active_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def load(result: TransformResult, db_path: str, report_path: str) -> None:
    """Persist results to the database and write the HTML report file.

    Prints connection info and completion timestamp, matching original
    behaviour.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    load_db(result, db_path)

    report_html = generate_report(result)
    Path(report_path).write_text(report_html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    entries = extract(LOG_FILE)
    result = transform(entries)
    load(result, DB_PATH, REPORT_PATH)


# ---------------------------------------------------------------------------
# Seed data for smoke-testing (preserves original __main__ behaviour)
# ---------------------------------------------------------------------------

_SEED_LOG_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]

if __name__ == "__main__":
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text("\n".join(_SEED_LOG_LINES) + "\n")
    run_pipeline()