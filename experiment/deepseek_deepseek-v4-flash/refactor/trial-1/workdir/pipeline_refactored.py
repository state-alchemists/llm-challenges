"""ETL pipeline that turns server logs into a metrics report.

Reads a server log file, extracts structured events, aggregates error
counts / API latency / active sessions, then loads the results into a
SQLite database and writes ``report.html``.

All configuration comes from environment variables:

    DB_PATH      SQLite database file  (default: metrics.db)
    LOG_FILE     server log to process (default: server.log)
    REPORT_FILE  HTML report path      (default: report.html)
    DB_HOST, DB_PORT, DB_USER, DB_PASS
                 reserved for a client/server backend; the SQLite
                 backend does not use them, but they are read from the
                 environment so credentials are never hardcoded.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Pipeline configuration, populated from environment variables."""

    db_path: str
    log_file: str
    report_file: str
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = ""
    db_pass: str = ""

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables, with safe defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            report_file=os.getenv("REPORT_FILE", "report.html"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", ""),
            db_pass=os.getenv("DB_PASS", ""),
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Example log lines:
#   2024-01-01 12:00:00 INFO User 42 logged in
#   2024-01-01 12:05:00 ERROR Database timeout
#   2024-01-01 12:08:00 INFO API /users/profile took 250ms
#   2024-01-01 12:09:00 WARN Memory usage at 87%
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|WARN|ERROR) (?P<body>.*)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\S+)(?: (?P<action>.*))?$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")


@dataclass(frozen=True)
class LogEvent:
    """One parsed log line."""

    timestamp: str
    level: str
    kind: str  # one of: ERROR, WARN, USER, API
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


def extract_log_events(log_file: str | Path) -> list[LogEvent]:
    """Read ``log_file`` and parse every line into a LogEvent.

    Returns an empty list when the file does not exist.
    """
    path = Path(log_file)
    if not path.is_file():
        return []
    events: list[LogEvent] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)
    return events


def parse_log_line(line: str) -> LogEvent | None:
    """Parse a single log line, or return None if it matches no pattern."""
    match = _LINE_RE.match(line.strip())
    if match is None:
        return None
    timestamp = match.group("ts")
    level = match.group("level")
    body = match.group("body")
    if not body:
        return None
    if level == "ERROR":
        return LogEvent(timestamp, level, "ERROR", message=body)
    if level == "WARN":
        return LogEvent(timestamp, level, "WARN", message=body)
    user_match = _USER_RE.match(body)
    if user_match is not None:
        return LogEvent(
            timestamp,
            level,
            "USER",
            user_id=user_match.group("uid"),
            action=user_match.group("action") or "",
        )
    api_match = _API_RE.match(body)
    if api_match is not None:
        return LogEvent(
            timestamp,
            level,
            "API",
            endpoint=api_match.group("endpoint"),
            duration_ms=int(api_match.group("ms")) if api_match.group("ms") else 0,
        )
    return None


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_error_summary(events: Iterable[LogEvent]) -> dict[str, int]:
    """Count occurrences of each distinct ERROR message, in first-seen order."""
    counts: dict[str, int] = {}
    for event in events:
        if event.kind == "ERROR" and event.message:
            counts[event.message] = counts.get(event.message, 0) + 1
    return counts


def transform_api_latency(events: Iterable[LogEvent]) -> dict[str, float]:
    """Average duration in ms per API endpoint, in first-seen order."""
    timings: dict[str, list[int]] = {}
    for event in events:
        if event.kind == "API" and event.endpoint is not None:
            timings.setdefault(event.endpoint, []).append(event.duration_ms or 0)
    return {
        endpoint: sum(samples) / len(samples)
        for endpoint, samples in timings.items()
    }


def transform_active_sessions(events: Iterable[LogEvent]) -> set[str]:
    """Replay login/logout events; return the set of user ids still active."""
    sessions: set[str] = set()
    for event in events:
        if event.kind != "USER" or event.user_id is None:
            continue
        action = event.action or ""
        if "logged in" in action:
            sessions.add(event.user_id)
        elif "logged out" in action:
            sessions.discard(event.user_id)
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

_CREATE_ERRORS_SQL = (
    "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
)
_CREATE_API_METRICS_SQL = (
    "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
)
_INSERT_ERROR_SQL = "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)"
_INSERT_API_METRICS_SQL = (
    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)"
)


def load_metrics_to_db(
    db_path: str,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Persist aggregated metrics into SQLite using parameterized queries."""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(_CREATE_ERRORS_SQL)
            conn.execute(_CREATE_API_METRICS_SQL)
            now = datetime.datetime.now().isoformat(sep=" ")
            conn.executemany(
                _INSERT_ERROR_SQL,
                [(now, message, count) for message, count in error_summary.items()],
            )
            conn.executemany(
                _INSERT_API_METRICS_SQL,
                [(now, endpoint, avg_ms) for endpoint, avg_ms in api_latency.items()],
            )
    finally:
        conn.close()


def render_report(
    report_file: str | Path,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: set[str],
) -> None:
    """Write ``report_file`` with the error summary, latency table, and session count."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in error_summary.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines += [
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for endpoint, avg_ms in api_latency.items():
        lines.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{avg_ms:.1f}</td></tr>"
        )
    lines += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    with open(report_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(config: Config | None = None) -> int:
    """Run the full Extract -> Transform -> Load pipeline."""
    cfg = config or Config.from_env()
    events = extract_log_events(cfg.log_file)
    error_summary = transform_error_summary(events)
    api_latency = transform_api_latency(events)
    active_sessions = transform_active_sessions(events)
    load_metrics_to_db(cfg.db_path, error_summary, api_latency)
    render_report(cfg.report_file, error_summary, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")
    return 0


def _write_sample_log(log_file: str) -> None:
    """Create a demo log file so a fresh checkout still produces a report."""
    sample = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    with open(log_file, "w", encoding="utf-8") as fh:
        fh.write(sample)


if __name__ == "__main__":
    cfg = Config.from_env()
    if not os.path.exists(cfg.log_file):
        _write_sample_log(cfg.log_file)
    raise SystemExit(main(cfg))
