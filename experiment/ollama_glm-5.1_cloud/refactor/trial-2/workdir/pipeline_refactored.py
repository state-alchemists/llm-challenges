"""Pipeline to extract server logs, transform them into metrics, and load a report.

Reads server logs, parses error messages, API latencies, and user sessions,
then persists aggregated metrics to SQLite and writes an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — all values come from environment variables.
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing.
# ---------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<rest>.*)$"
)
_ERROR_RE = re.compile(r"^(?P<message>.+)$")
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$")
_WARN_RE = re.compile(r"^(?P<message>.+)$")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class ErrorEntry:
    """A single parsed error line."""

    timestamp: str
    message: str


@dataclass
class ApiCall:
    """A single parsed API call with latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarningEntry:
    """A single parsed warning line."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A single parsed user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ParsedLog:
    """Aggregation of all parsed log entries."""

    errors: list[ErrorEntry] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract — read and parse log lines.
# ---------------------------------------------------------------------------
def extract(log_path: str) -> ParsedLog:
    """Read the log file and parse each line into structured data.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A ParsedLog containing categorised, typed entries.
    """
    parsed = ParsedLog()
    if not Path(log_path).exists():
        return parsed

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line.strip())
            if not match:
                continue
            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                m = _ERROR_RE.match(rest)
                if m:
                    parsed.errors.append(
                        ErrorEntry(timestamp=timestamp, message=m.group("message"))
                    )
            elif level == "INFO":
                if "User" in rest:
                    m = _USER_RE.match(rest)
                    if m:
                        parsed.user_events.append(
                            UserEvent(
                                timestamp=timestamp,
                                user_id=m.group("uid"),
                                action=m.group("action"),
                            )
                        )
                elif "API" in rest:
                    m = _API_RE.match(rest)
                    if m:
                        parsed.api_calls.append(
                            ApiCall(
                                timestamp=timestamp,
                                endpoint=m.group("endpoint"),
                                latency_ms=int(m.group("ms")),
                            )
                        )
            elif level == "WARN":
                m = _WARN_RE.match(rest)
                if m:
                    parsed.warnings.append(
                        WarningEntry(timestamp=timestamp, message=m.group("message"))
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform — compute aggregated metrics.
# ---------------------------------------------------------------------------
@dataclass
class ErrorSummary:
    """Error message with its occurrence count."""

    message: str
    count: int


@dataclass
class LatencySummary:
    """Average latency for an API endpoint."""

    endpoint: str
    avg_ms: float


@dataclass
class ReportData:
    """All data needed to render the HTML report."""

    error_summaries: list[ErrorSummary]
    latency_summaries: list[LatencySummary]
    active_sessions: int


def transform(parsed: ParsedLog) -> ReportData:
    """Aggregate parsed log entries into report-ready summaries.

    Args:
        parsed: The extracted log data.

    Returns:
        A ReportData with error counts, average latencies, and active session count.
    """
    # Error counts
    error_counts: dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
    error_summaries = [
        ErrorSummary(message=msg, count=count)
        for msg, count in error_counts.items()
    ]

    # API latency averages
    endpoint_latencies: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.latency_ms)
    latency_summaries = [
        LatencySummary(
            endpoint=ep,
            avg_ms=round(sum(times) / len(times), 1),
        )
        for ep, times in endpoint_latencies.items()
    ]

    # Active sessions (logged-in users without a matching logout)
    sessions: dict[str, str] = {}
    for event in parsed.user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    active_sessions = len(sessions)

    return ReportData(
        error_summaries=error_summaries,
        latency_summaries=latency_summaries,
        active_sessions=active_sessions,
    )


# ---------------------------------------------------------------------------
# Load — persist to database and write report.
# ---------------------------------------------------------------------------
def _persist_to_db(db_path: str, data: ReportData) -> None:
    """Insert aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        data: Aggregated report data to persist.
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
        for summary in data.error_summaries:
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, summary.message, summary.count),
            )
        for summary in data.latency_summaries:
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, summary.endpoint, summary.avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def _render_html(data: ReportData) -> str:
    """Render the report data as an HTML document.

    Args:
        data: Aggregated report data.

    Returns:
        Complete HTML string for the report.
    """
    parts: list[str] = []
    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")

    # Error summary
    parts.append("<h1>Error Summary</h1>")
    parts.append("<ul>")
    for summary in data.error_summaries:
        parts.append(
            f"<li><b>{summary.message}</b>: {summary.count} occurrences</li>"
        )
    parts.append("</ul>")

    # API latency table
    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for summary in data.latency_summaries:
        parts.append(
            f"<tr><td>{summary.endpoint}</td><td>{summary.avg_ms}</td></tr>"
        )
    parts.append("</table>")

    # Active sessions
    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{data.active_sessions} user(s) currently active</p>")

    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def load(db_path: str, report_path: str, data: ReportData) -> None:
    """Persist metrics to the database and write the HTML report.

    Args:
        db_path: Path to the SQLite database.
        report_path: Filesystem path for the output HTML report.
        data: Aggregated report data.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    _persist_to_db(db_path, data)

    html = _render_html(data)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    parsed = extract(LOG_FILE)
    data = transform(parsed)
    load(DB_PATH, "report.html", data)


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()