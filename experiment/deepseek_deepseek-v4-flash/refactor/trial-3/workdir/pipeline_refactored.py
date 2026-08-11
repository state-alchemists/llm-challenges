"""Process server logs into a SQLite database and an HTML report.

Follows an Extract -> Transform -> Load structure:

- Extract:   parse each log line into a structured ``LogEvent`` using regexes.
- Transform: aggregate events into error counts, per-endpoint API latency,
             and the number of active user sessions.
- Load:      persist the aggregates to SQLite with parameterized queries and
             render ``report.html`` with the same information the original
             script produced (error summary, API latency table, active
             session count).

All configuration is read from environment variables with sensible defaults:

    LOG_FILE    - path to the server log to process        (default: server.log)
    DB_PATH     - path to the SQLite database              (default: metrics.db)
    REPORT_PATH - path of the generated HTML report        (default: report.html)
    DB_HOST     - database hostname (kept for parity with the original
                  config; SQLite does not require a server) (default: localhost)
    DB_PORT     - database port                            (default: 5432)
    DB_USER     - database user                            (default: admin)
    DB_PASS     - database password                        (default: "")

The connection credentials are read into ``PipelineConfig`` even though the
SQLite backend ignores them, so the script stays ready for a remote database
without hardcoding secrets.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------

# Lines look like: 2024-01-01 12:00:00 ERROR Database timeout
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>[A-Z]+)\s+(?P<body>.+)$"
)
# e.g. "User 42 logged in" / "User 42 logged out"
_USER_RE = re.compile(r"User (?P<uid>\S+) (?P<action>.*)")
# e.g. "API /users/profile took 250ms"
_API_RE = re.compile(r"API (?P<endpoint>\S+)")
_TOOK_RE = re.compile(r"took (?P<ms>\d+)ms")

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One parsed line from the server log."""

    timestamp: str
    level: str
    kind: str  # "ERROR" | "WARN" | "USER" | "API"
    message: str = ""
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Runtime settings; every value can be overridden via environment variables."""

    db_path: Path
    log_path: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(slots=True)
class ReportData:
    """Aggregated values that feed both the database and the HTML report."""

    error_counts: dict[str, int]
    endpoint_latencies: dict[str, list[int]]
    active_sessions: int


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> PipelineConfig:
    """Read all configuration from environment variables with defaults."""
    return PipelineConfig(
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        log_path=Path(os.getenv("LOG_FILE", "server.log")),
        report_path=Path(os.getenv("REPORT_PATH", "report.html")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_events(log_path: Path) -> list[LogEvent]:
    """Extract structured events from every line of the server log."""
    if not log_path.is_file():
        return []
    events: list[LogEvent] = []
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            event = _parse_line(line)
            if event is not None:
                events.append(event)
    return events


def _parse_line(line: str) -> LogEvent | None:
    """Parse one log line into a LogEvent, or None if it is unrecognized."""
    match = _LOG_LINE_RE.match(line.strip())
    if match is None:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    body = match.group("body")

    if level == "ERROR":
        return LogEvent(timestamp, level, "ERROR", message=body.strip())
    if level == "WARN":
        return LogEvent(timestamp, level, "WARN", message=body.strip())

    if level == "INFO":
        user_match = _USER_RE.search(body)
        if user_match is not None:
            return LogEvent(
                timestamp,
                level,
                "USER",
                user_id=user_match.group("uid"),
                action=user_match.group("action").strip(),
            )
        api_match = _API_RE.search(body)
        if api_match is not None:
            took_match = _TOOK_RE.search(body)
            duration_ms = int(took_match.group("ms")) if took_match else 0
            return LogEvent(
                timestamp,
                level,
                "API",
                endpoint=api_match.group("endpoint"),
                duration_ms=duration_ms,
            )

    return None


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_events(events: Iterable[LogEvent]) -> ReportData:
    """Aggregate events into error counts, API latencies, and active sessions."""
    error_counts: dict[str, int] = {}
    endpoint_latencies: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for event in events:
        if event.kind == "ERROR":
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
        elif event.kind == "API":
            endpoint_latencies.setdefault(event.endpoint or "", []).append(
                event.duration_ms or 0
            )
        elif event.kind == "USER":
            uid = event.user_id or ""
            action = event.action or ""
            if "logged in" in action:
                sessions[uid] = event.timestamp
            elif "logged out" in action and uid in sessions:
                sessions.pop(uid)

    return ReportData(
        error_counts=error_counts,
        endpoint_latencies=endpoint_latencies,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_data(data: ReportData, db_path: Path) -> None:
    """Persist the aggregates into SQLite using parameterized queries."""
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
            )

            # ISO text avoids the deprecated datetime adapter for sqlite3.
            now = dt.datetime.now().isoformat(sep=" ")
            conn.executemany(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                [(now, message, count) for message, count in data.error_counts.items()],
            )
            conn.executemany(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                [
                    (now, endpoint, sum(times) / len(times))
                    for endpoint, times in data.endpoint_latencies.items()
                ],
            )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(data: ReportData) -> str:
    """Render the HTML report: error summary, API latency table, active sessions."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    lines.extend(
        f"<li><b>{message}</b>: {count} occurrences</li>"
        for message, count in data.error_counts.items()
    )
    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in data.endpoint_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{data.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def write_report(data: ReportData, report_path: Path) -> None:
    """Write the generated HTML report to disk."""
    report_path.write_text(generate_report(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _write_sample_log(log_path: Path) -> None:
    """Create the demo log used by the original script when none exists."""
    log_path.write_text(_SAMPLE_LOG, encoding="utf-8")


def main() -> None:
    """Run the full extract -> transform -> load pipeline end to end."""
    config = load_config()
    if not config.log_path.is_file():
        _write_sample_log(config.log_path)

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    events = extract_events(config.log_path)
    data = transform_events(events)
    load_data(data, config.db_path)
    write_report(data, config.report_path)

    print(f"Job finished at {dt.datetime.now()}")


if __name__ == "__main__":
    main()
