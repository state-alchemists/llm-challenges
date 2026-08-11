"""Server log analysis pipeline (refactored).

Extracts events from a server log file, transforms them into aggregated
metrics (error counts, API latency averages, active session count), loads
the metrics into a SQLite database, and renders a static HTML report.

Refactor highlights compared to the original ``pipeline.py``:

* All configuration (file paths, DB credentials) comes from environment
  variables instead of hardcoded module constants.
* SQL writes use parameterized queries instead of string interpolation.
* The one monolithic function is split into Extract -> Transform -> Load
  stages with a small ``main`` orchestrator.
* Log lines are parsed with compiled regular expressions instead of
  fragile ``str.split`` / substring checks.
* Every function is typed and documented.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# --- Configuration -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    log_path: Path
    db_path: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Build a Config from environment variables, falling back to defaults."""
    return Config(
        log_path=Path(os.getenv("LOG_FILE", "server.log")),
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        report_path=Path(os.getenv("REPORT_PATH", "report.html")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


# --- Extract -----------------------------------------------------------------


_TIMESTAMP_PATTERN = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"

#: Matches the fixed prefix shared by every log line: timestamp, level, body.
LOG_LINE_RE = re.compile(
    rf"^(?P<timestamp>{_TIMESTAMP_PATTERN}) (?P<level>ERROR|INFO|WARN) (?P<body>.*)$"
)
#: Matches INFO user events, e.g. "User 42 logged in".
INFO_USER_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>logged in|logged out)$")
#: Matches INFO API events, e.g. "API /users/profile took 250ms".
INFO_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


@dataclass(frozen=True, slots=True)
class LogEvent:
    """A single parsed log line; fields are populated according to level."""

    timestamp: str
    level: str
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


def parse_line(line: str) -> LogEvent | None:
    """Parse one log line into a LogEvent, or return None if malformed."""
    match = LOG_LINE_RE.match(line)
    if match is None:
        return None
    level = match.group("level")
    body = match.group("body")

    if level == "INFO":
        user_match = INFO_USER_RE.match(body)
        if user_match is not None:
            return LogEvent(
                timestamp=match.group("timestamp"),
                level=level,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )
        api_match = INFO_API_RE.match(body)
        if api_match is not None:
            return LogEvent(
                timestamp=match.group("timestamp"),
                level=level,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("duration")),
            )

    return LogEvent(timestamp=match.group("timestamp"), level=level, message=body)


def ensure_sample_log(log_path: Path) -> None:
    """Create a small sample log when the configured log file is missing."""
    if log_path.exists():
        return
    sample = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    log_path.write_text(sample, encoding="utf-8")


def extract_logs(log_path: Path) -> list[LogEvent]:
    """Read the server log and parse every line into a LogEvent."""
    ensure_sample_log(log_path)
    events: list[LogEvent] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        event = parse_line(line)
        if event is not None:
            events.append(event)
    return events


# --- Transform ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReportData:
    """Aggregated metrics shared by the DB load and the HTML report."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_sessions: int


def transform_logs(events: list[LogEvent]) -> ReportData:
    """Aggregate events into error counts, API latency, and session count.

    Sessions are tracked by replaying login/logout events in log order; the
    number of users still logged in at the end is the active-session figure.
    """
    error_counts: dict[str, int] = {}
    durations: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for event in events:
        if event.level == "ERROR" and event.message is not None:
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
        elif event.user_id is not None:
            if event.action == "logged in":
                sessions[event.user_id] = event.timestamp
            elif event.action == "logged out":
                sessions.pop(event.user_id, None)
        elif event.endpoint is not None:
            durations.setdefault(event.endpoint, []).append(
                event.duration_ms if event.duration_ms is not None else 0
            )

    endpoint_avg_ms = {
        endpoint: sum(times) / len(times) for endpoint, times in durations.items()
    }
    return ReportData(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_sessions=len(sessions),
    )


# --- Load --------------------------------------------------------------------


def load_metrics(db_path: Path, report: ReportData) -> None:
    """Persist aggregated metrics into SQLite with parameterized queries."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now: str = datetime.datetime.now().isoformat(sep=" ")
        conn.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            [(now, message, count) for message, count in report.error_counts.items()],
        )
        conn.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            [(now, endpoint, avg) for endpoint, avg in report.endpoint_avg_ms.items()],
        )


# --- Report ------------------------------------------------------------------


def generate_report(report: ReportData, report_path: Path) -> None:
    """Render error summary, API latency table, and session count as HTML.

    Strings originating from log data are HTML-escaped to prevent markup
    injection in the generated report.
    """
    error_items = "\n".join(
        f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        for message, count in report.error_counts.items()
    )
    latency_rows = "\n".join(
        f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg, 1)}</td></tr>"
        for endpoint, avg in report.endpoint_avg_ms.items()
    )

    out = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        "<h1>Error Summary</h1>\n<ul>\n"
        + error_items
        + "\n</ul>\n"
        + "<h2>API Latency</h2>\n<table border='1'>\n"
        + "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        + latency_rows
        + "\n</table>\n"
        + "<h2>Active Sessions</h2>\n"
        + f"<p>{report.active_sessions} user(s) currently active</p>\n"
        + "</body>\n</html>"
    )
    report_path.write_text(out, encoding="utf-8")


def main() -> None:
    """Run the extract -> transform -> load -> report pipeline."""
    config = load_config()
    events = extract_logs(config.log_path)
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    report = transform_logs(events)
    load_metrics(config.db_path, report)
    generate_report(report, config.report_path)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
