"""ETL pipeline: parse server logs, aggregate metrics, and emit an HTML report.

All configuration comes from environment variables; log lines are parsed
with regular expressions; aggregates are persisted to SQLite via
parameterized queries; and the final report keeps the original sections
(error summary, API latency table, active session count).

Pipeline stages:
    extract   -> read + regex-parse the log file
    transform -> group events into error counts / API latencies / sessions
    load      -> persist aggregates to SQLite and write report.html
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) (?P<message>.*)$"
)
_USER_EVENT_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")
_API_EVENT_RE = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$"
)


@dataclass(frozen=True)
class LogEvent:
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass(frozen=True)
class ReportData:
    """Aggregated metrics that back the generated report."""

    error_counts: dict[str, int]
    api_latencies: dict[str, list[int]]
    active_sessions: dict[str, str]


@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    log_path: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str  # reserved for the DB backend; SQLite does not use it
    report_path: Path

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables, falling back to defaults."""
        return cls(
            log_path=Path(os.getenv("LOG_FILE", "server.log")),
            db_path=Path(os.getenv("DB_PATH", "metrics.db")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", ""),
            report_path=Path(os.getenv("REPORT_FILE", "report.html")),
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_logs(log_path: Path) -> list[LogEvent]:
    """Read the log file and parse each line into a structured LogEvent.

    Lines that do not match the expected timestamp/level/message shape are
    skipped. A missing log file yields an empty event list rather than an
    error, matching the original behavior.
    """
    events: list[LogEvent] = []
    if not log_path.exists():
        return events
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = _LOG_LINE_RE.match(line.strip())
            if match is not None:
                events.append(
                    LogEvent(
                        timestamp=match.group("timestamp"),
                        level=match.group("level"),
                        message=match.group("message"),
                    )
                )
    return events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_events(events: list[LogEvent]) -> ReportData:
    """Group raw log events into error counts, API latencies, and sessions.

    ERROR lines are counted per unique message. INFO lines starting with
    ``User`` update the active-session map; INFO lines starting with ``API``
    record endpoint latency samples. All other levels are ignored, as in the
    original pipeline.
    """
    error_counts: dict[str, int] = {}
    api_latencies: dict[str, list[int]] = {}
    active_sessions: dict[str, str] = {}

    for event in events:
        if event.level == "ERROR":
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
            continue
        if event.level != "INFO":
            continue
        user_match = _USER_EVENT_RE.match(event.message)
        if user_match is not None:
            _track_session(user_match, event.timestamp, active_sessions)
            continue
        api_match = _API_EVENT_RE.match(event.message)
        if api_match is not None:
            _record_api_call(api_match, api_latencies)

    return ReportData(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=active_sessions,
    )


def _track_session(
    match: re.Match[str],
    timestamp: str,
    active_sessions: dict[str, str],
) -> None:
    """Apply a User event to the active-session map."""
    uid = match.group("uid")
    action = match.group("action")
    if "logged in" in action:
        active_sessions[uid] = timestamp
    elif "logged out" in action and uid in active_sessions:
        del active_sessions[uid]


def _record_api_call(
    match: re.Match[str],
    api_latencies: dict[str, list[int]],
) -> None:
    """Append an API latency sample to the per-endpoint list."""
    endpoint = match.group("endpoint")
    duration_ms = match.group("duration_ms") or "0"
    api_latencies.setdefault(endpoint, []).append(int(duration_ms))


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_metrics_to_db(db_path: Path, data: ReportData, timestamp: str) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Creates the metrics tables when missing, inserts one row per error
    message and one per endpoint, and commits.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_schema(conn)
        for message, count in data.error_counts.items():
            conn.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (timestamp, message, count),
            )
        for endpoint, latencies in data.api_latencies.items():
            avg_ms = sum(latencies) / len(latencies)
            conn.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (timestamp, endpoint, avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create the errors and api_metrics tables if they do not exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def generate_report(data: ReportData) -> str:
    """Build the HTML report: error summary, API latency table, session count."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in data.error_counts.items():
        lines.append(
            f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        )
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, latencies in data.api_latencies.items():
        avg_ms = sum(latencies) / len(latencies)
        lines.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(data.active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines) + "\n"


def write_report(report_path: Path, content: str) -> None:
    """Write the generated HTML report to disk."""
    report_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the ETL pipeline: extract, transform, load, and report."""
    config = Config.from_env()
    events = extract_logs(config.log_path)
    data = transform_events(events)
    now = datetime.datetime.now().isoformat(sep=" ")
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    load_metrics_to_db(config.db_path, data, now)
    report_html = generate_report(data)
    write_report(config.report_path, report_html)
    print(f"Job finished at {now}")


if __name__ == "__main__":
    main()
