"""Refactored server-log pipeline: Extract -> Transform -> Load.

Reads a server log, derives error / API-latency / session metrics, persists
the aggregates to SQLite using parameterized queries, and renders
``report.html``.

All configuration comes from environment variables (the original hardcoded
values are removed):

    LOG_FILE   path to the server log            (default: server.log)
    DB_PATH    path to the SQLite database file  (default: metrics.db)
    DB_HOST    DB host, connection metadata      (default: localhost)
    DB_PORT    DB port, connection metadata      (default: 5432)
    DB_USER    DB user, connection metadata      (default: admin)
    DB_PASS    DB password, connection metadata  (default: empty)

Note on credentials: the original script announced DB_HOST/DB_PORT/DB_USER
but actually stored everything in a local SQLite file. Storage still targets
the SQLite file at DB_PATH; the credential variables are read from the
environment (never hardcoded) and used as the announced connection metadata.
The password is deliberately never printed.
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

DEFAULT_LOG_FILE = "server.log"
DEFAULT_DB_PATH = "metrics.db"

# Matches the fixed-width prefix of every log line:
#   "YYYY-MM-DD HH:MM:SS LEVEL <message>"
_LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) (?P<message>.+)$"
)
# INFO message body shapes:
#   "User 42 logged in"
_USER_ACTION_PATTERN = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
#   "API /users/profile took 250ms"
_API_CALL_PATTERN = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$"
)


@dataclass
class Config:
    """Runtime configuration, sourced from environment variables."""

    log_file: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class LogEvent:
    """A single structured log line."""

    timestamp: str
    level: str
    message: str


@dataclass
class ReportData:
    """Aggregated metrics used by both the DB load and the HTML report."""

    error_counts: dict[str, int]
    api_latency_ms: dict[str, float]
    active_sessions: int


def load_config() -> Config:
    """Read pipeline configuration from environment variables."""
    return Config(
        log_file=Path(os.getenv("LOG_FILE", DEFAULT_LOG_FILE)),
        db_path=Path(os.getenv("DB_PATH", DEFAULT_DB_PATH)),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


def _write_sample_log(log_path: Path) -> None:
    """Seed a minimal log so the pipeline is runnable on first use."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    log_path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_events(log_path: Path) -> list[LogEvent]:
    """Parse every log line into a structured LogEvent.

    Lines that do not match the expected format are skipped.
    """
    events: list[LogEvent] = []
    if not log_path.exists():
        return events
    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            match = _LOG_LINE_PATTERN.match(line.strip())
            if match is None:
                continue
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


def _aggregate_errors(events: list[LogEvent]) -> dict[str, int]:
    """Count occurrences of each ERROR message, preserving first-seen order."""
    counts: dict[str, int] = {}
    for event in events:
        if event.level == "ERROR":
            counts[event.message] = counts.get(event.message, 0) + 1
    return counts


def _aggregate_api_latency(events: list[LogEvent]) -> dict[str, float]:
    """Compute the average latency (ms) per API endpoint, in first-seen order."""
    per_endpoint: dict[str, list[int]] = {}
    for event in events:
        if event.level != "INFO":
            continue
        match = _API_CALL_PATTERN.match(event.message)
        if match is None:
            continue
        endpoint = match.group("endpoint")
        duration = int(match.group("duration_ms") or "0")
        per_endpoint.setdefault(endpoint, []).append(duration)
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in per_endpoint.items()
    }


def _count_active_sessions(events: list[LogEvent]) -> int:
    """Count users currently logged in based on User login/logout lines."""
    sessions: dict[str, str] = {}
    for event in events:
        if event.level != "INFO":
            continue
        match = _USER_ACTION_PATTERN.match(event.message)
        if match is None:
            continue
        user_id = match.group("user_id")
        action = match.group("action")
        if "logged in" in action:
            sessions[user_id] = event.timestamp
        elif "logged out" in action and user_id in sessions:
            del sessions[user_id]
    return len(sessions)


def transform_events(events: list[LogEvent]) -> ReportData:
    """Derive error counts, API latency averages, and the active session count."""
    return ReportData(
        error_counts=_aggregate_errors(events),
        api_latency_ms=_aggregate_api_latency(events),
        active_sessions=_count_active_sessions(events),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_metrics_to_db(data: ReportData, config: Config) -> None:
    """Persist error counts and API latency averages to SQLite.

    All queries are parameterized — values are passed as bind parameters,
    never interpolated into SQL text.
    """
    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )
    conn = sqlite3.connect(str(config.db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now = datetime.datetime.now().isoformat(sep=" ")
        for message, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, avg_ms in data.api_latency_ms.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def generate_report(data: ReportData, report_path: Path) -> None:
    """Render report.html with the error summary, latency table, and session count."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for error_message, count in data.error_counts.items():
        lines.append(
            f"<li><b>{html.escape(error_message)}</b>: {count} occurrences</li>"
        )
    lines += [
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for endpoint, avg_ms in data.api_latency_ms.items():
        lines.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    lines += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{data.active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Run the full extract -> transform -> load pipeline."""
    config = load_config()
    if not config.log_file.exists():
        _write_sample_log(config.log_file)
    events = extract_events(config.log_file)
    data = transform_events(events)
    load_metrics_to_db(data, config)
    generate_report(data, Path("report.html"))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
