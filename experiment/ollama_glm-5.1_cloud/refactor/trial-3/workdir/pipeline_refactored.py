"""Server-log ETL pipeline: extract, transform, load into SQLite and HTML report.

Configuration is read from environment variables with sensible defaults:
  LOG_FILE   – path to the server log   (default: server.log)
  DB_PATH    – path to the SQLite file  (default: metrics.db)
  DB_HOST    – database host            (default: localhost)
  DB_PORT    – database port            (default: 5432)
  DB_USER    – database user            (default: admin)
  DB_PASS    – database password        (default: password123)

Usage:
    python pipeline_refactored.py
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Log-line patterns (regex)
# ---------------------------------------------------------------------------

# 2024-01-01 12:00:00 INFO ...
_RE_TIMESTAMP = r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
_RE_LEVEL = r"(?P<level>ERROR|WARN|INFO)"
_RE_BASE = rf"^{_RE_TIMESTAMP} {_RE_LEVEL} (?P<msg>.+)$"

RE_LOG_LINE = re.compile(_RE_BASE)

# 2024-01-01 12:00:00 INFO User 42 logged in
RE_USER_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"User (?P<uid>\S+) (?P<action>.+)$"
)

# 2024-01-01 12:08:00 INFO API /users/profile took 250ms
RE_API_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"API (?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user login / logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with latency measurement."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarnEvent:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Aggregation of all parsed log entries."""

    errors: list[ErrorEvent] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarnEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract – read and parse the log file
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> Optional[ErrorEvent | UserEvent | ApiCall | WarnEvent]:
    """Parse a single log line into a typed event, or *None* if unrecognised."""
    stripped = line.rstrip("\n")
    if not stripped:
        return None

    # Try the most specific patterns first
    m = RE_API_LINE.match(stripped)
    if m:
        return ApiCall(
            timestamp=m.group("ts"),
            endpoint=m.group("endpoint"),
            duration_ms=int(m.group("duration")),
        )

    m = RE_USER_LINE.match(stripped)
    if m:
        return UserEvent(
            timestamp=m.group("ts"),
            user_id=m.group("uid"),
            action=m.group("action"),
        )

    m = RE_LOG_LINE.match(stripped)
    if m:
        level = m.group("level")
        ts = m.group("ts")
        msg = m.group("msg")
        if level == "ERROR":
            return ErrorEvent(timestamp=ts, message=msg)
        if level == "WARN":
            return WarnEvent(timestamp=ts, message=msg)
        # INFO lines that didn't match USER/API patterns are ignored
        return None

    return None


def extract(log_path: str) -> ParsedLog:
    """Read *log_path* and return a :class:`ParsedLog` of typed events."""
    parsed = ParsedLog()
    path = Path(log_path)
    if not path.exists():
        return parsed

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            event = parse_log_line(line)
            if isinstance(event, ErrorEvent):
                parsed.errors.append(event)
            elif isinstance(event, UserEvent):
                parsed.user_events.append(event)
            elif isinstance(event, ApiCall):
                parsed.api_calls.append(event)
            elif isinstance(event, WarnEvent):
                parsed.warnings.append(event)

    return parsed


# ---------------------------------------------------------------------------
# Transform – aggregate raw events into summary structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorSummary:
    """Count of each distinct error message."""

    message: str
    count: int


@dataclass
class ApiLatency:
    """Average latency for an API endpoint."""

    endpoint: str
    avg_ms: float


@dataclass
class TransformResult:
    """All aggregated data needed for the report and DB load."""

    error_summaries: list[ErrorSummary] = field(default_factory=list)
    api_latencies: list[ApiLatency] = field(default_factory=list)
    active_session_count: int = 0


def transform(parsed: ParsedLog) -> TransformResult:
    """Aggregate extracted events into summary structures."""
    # Error summary: count occurrences per distinct message
    error_counts: dict[str, int] = {}
    for err in parsed.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    error_summaries = [
        ErrorSummary(message=msg, count=count)
        for msg, count in error_counts.items()
    ]

    # API latency: average duration per endpoint
    endpoint_times: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.duration_ms)

    api_latencies = [
        ApiLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in endpoint_times.items()
    ]

    # Active sessions: users logged in but not yet logged out
    active_sessions: set[str] = set()
    for evt in parsed.user_events:
        if "logged in" in evt.action:
            active_sessions.add(evt.user_id)
        elif "logged out" in evt.action and evt.user_id in active_sessions:
            active_sessions.discard(evt.user_id)

    return TransformResult(
        error_summaries=error_summaries,
        api_latencies=api_latencies,
        active_session_count=len(active_sessions),
    )


# ---------------------------------------------------------------------------
# Load – persist to SQLite and write the HTML report
# ---------------------------------------------------------------------------


def load_to_db(
    db_path: str,
    error_summaries: list[ErrorSummary],
    api_latencies: list[ApiLatency],
) -> None:
    """Insert aggregated data into SQLite using parameterized queries."""
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
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

        for summary in error_summaries:
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, summary.message, summary.count),
            )

        for latency in api_latencies:
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, latency.endpoint, latency.avg_ms),
            )

        conn.commit()
    finally:
        conn.close()

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")


def render_html(result: TransformResult) -> str:
    """Render an HTML report from the aggregated data."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for summary in result.error_summaries:
        lines.append(
            f"<li><b>{summary.message}</b>: {summary.count} occurrences</li>"
        )

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for latency in result.api_latencies:
        lines.append(
            f"<tr><td>{latency.endpoint}</td>"
            f"<td>{round(latency.avg_ms, 1)}</td></tr>"
        )

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{result.active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def load_report(result: TransformResult, report_path: str = "report.html") -> None:
    """Write the HTML report to disk."""
    html = render_html(result)
    Path(report_path).write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full ETL pipeline: extract, transform, load."""
    parsed = extract(LOG_FILE)
    result = transform(parsed)
    load_to_db(DB_PATH, result.error_summaries, result.api_latencies)
    load_report(result)
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