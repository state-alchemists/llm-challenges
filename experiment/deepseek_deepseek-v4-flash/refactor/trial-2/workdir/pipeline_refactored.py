"""Server-log processing pipeline (refactored).

Extract -> Transform -> Load (ETL) pipeline that reads a server log,
aggregates error counts, per-endpoint API latency, and the active
session count, loads the aggregates into a SQLite database, and renders
an HTML report with the same sections as the original script: error
summary, API latency table, and active session count.

All configuration is read from environment variables:

    LOG_FILE  - path to the server log to process  (default: server.log)
    DB_PATH   - path to the SQLite database file   (default: metrics.db)
    DB_HOST   - database host, shown in the banner (default: localhost)
    DB_PORT   - database port, shown in the banner (default: 5432)
    DB_USER   - database user, shown in the banner (default: admin)
    DB_PASS   - database password                  (default: empty)

The host/port/user/password values describe the (Postgres-style)
connection the original script printed; the actual store here is the
SQLite file at DB_PATH, and the password is never echoed.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, NamedTuple

REPORT_FILE = "report.html"

# A standard log line: "YYYY-MM-DD HH:MM:SS LEVEL message".
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+)\s+(?P<message>.*)$"
)

# Session events: "User <id> <action>".
USER_ACTION_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.*)$")

# API events: "API <endpoint> took <N>ms" (duration optional).
API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$")


class LogEvent(NamedTuple):
    """One parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime configuration loaded from environment variables."""

    log_file: str
    db_path: str
    db_host: str
    db_port: str
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Build a PipelineConfig from environment variables.

        Falls back to the same defaults the original script hardcoded,
        so the pipeline still runs when no environment is configured.

        Returns:
            A fully populated PipelineConfig.
        """
        return cls(
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_path=os.getenv("DB_PATH", "metrics.db"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=os.getenv("DB_PORT", "5432"),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", ""),
        )


@dataclass
class ProcessedLogs:
    """Aggregated metrics derived from the log."""

    error_counts: dict[str, int] = field(default_factory=dict)
    api_latency_ms: dict[str, float] = field(default_factory=dict)
    active_sessions: int = 0


# --- Extract ---------------------------------------------------------


def extract_lines(log_path: Path) -> list[str]:
    """Read the raw lines of the server log.

    Args:
        log_path: Path to the server log file.

    Returns:
        The file's lines, or an empty list if the file does not exist.
    """
    if not log_path.is_file():
        return []
    return log_path.read_text(encoding="utf-8").splitlines()


def parse_line(line: str) -> LogEvent | None:
    """Parse one log line into a structured LogEvent.

    Args:
        line: A single line from the server log.

    Returns:
        A LogEvent, or None when the line does not match the expected
        format (blank lines and malformed entries are skipped).
    """
    match = LOG_LINE_RE.match(line)
    if match is None:
        return None
    return LogEvent(
        timestamp=match.group("timestamp"),
        level=match.group("level"),
        message=match.group("message"),
    )


# --- Transform -------------------------------------------------------


def _apply_user_action(
    active_sessions: dict[str, str], timestamp: str, message: str
) -> bool:
    """Record a login/logout event, if ``message`` is a User event.

    Args:
        active_sessions: Map of user id to login timestamp.
        timestamp: Timestamp of the log line.
        message: The message portion of the log line.

    Returns:
        True if the message was a User event, False otherwise.
    """
    match = USER_ACTION_RE.match(message)
    if match is None:
        return False
    user_id = match.group("user_id")
    action = match.group("action")
    if "logged in" in action:
        active_sessions[user_id] = timestamp
    elif "logged out" in action:
        active_sessions.pop(user_id, None)
    return True


def _record_api_call(api_times: dict[str, list[int]], message: str) -> None:
    """Append an API call's duration to its endpoint bucket, if any.

    Args:
        api_times: Map of endpoint to observed durations in ms.
        message: The message portion of the log line.
    """
    match = API_CALL_RE.match(message)
    if match is None:
        return
    endpoint = match.group("endpoint")
    duration_ms = match.group("duration_ms")
    api_times[endpoint].append(int(duration_ms) if duration_ms else 0)


def transform_events(lines: Iterable[str]) -> ProcessedLogs:
    """Aggregate raw log lines into error, latency, and session metrics.

    Args:
        lines: Iterable of raw log lines (typically from extract_lines).

    Returns:
        ProcessedLogs with error message counts, average API latency per
        endpoint in ms, and the number of sessions still active at the
        end of the log.
    """
    error_counts: dict[str, int] = {}
    api_times: dict[str, list[int]] = defaultdict(list)
    active_sessions: dict[str, str] = {}

    for line in lines:
        event = parse_line(line)
        if event is None:
            continue
        if event.level == "ERROR":
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
        elif event.level == "INFO":
            if not _apply_user_action(active_sessions, event.timestamp, event.message):
                _record_api_call(api_times, event.message)

    api_latency_ms = {
        endpoint: sum(times) / len(times) for endpoint, times in api_times.items()
    }
    return ProcessedLogs(
        error_counts=error_counts,
        api_latency_ms=api_latency_ms,
        active_sessions=len(active_sessions),
    )


# --- Load ------------------------------------------------------------


def load_metrics(processed: ProcessedLogs, db_path: Path) -> None:
    """Write aggregated metrics into the SQLite database.

    Creates the ``errors`` and ``api_metrics`` tables if needed and
    inserts one row per error message / endpoint. Values are passed as
    query parameters, never interpolated into the SQL text.

    Args:
        processed: Metrics produced by transform_events.
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now = datetime.datetime.now().isoformat(sep=" ")
        for message, count in processed.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, avg_ms in processed.api_latency_ms.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def generate_report(processed: ProcessedLogs, output_path: Path) -> None:
    """Render the processed metrics as an HTML report.

    Produces the same sections as the original script: error summary,
    API latency table, and active session count. Dynamic values are
    HTML-escaped so log content cannot inject markup.

    Args:
        processed: Metrics produced by transform_events.
        output_path: Where to write the report (report.html).
    """
    error_items = "".join(
        f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>\n"
        for message, count in processed.error_counts.items()
    )
    latency_rows = "".join(
        f"<tr><td>{html.escape(endpoint)}</td><td>{avg_ms:.1f}</td></tr>\n"
        for endpoint, avg_ms in processed.api_latency_ms.items()
    )
    report = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        "<h1>Error Summary</h1>\n<ul>\n"
        + error_items
        + "</ul>\n"
        "<h2>API Latency</h2>\n<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        + latency_rows
        + "</table>\n"
        "<h2>Active Sessions</h2>\n"
        f"<p>{processed.active_sessions} user(s) currently active</p>\n"
        "</body>\n</html>"
    )
    output_path.write_text(report, encoding="utf-8")


# --- Orchestration ---------------------------------------------------


def run_pipeline(config: PipelineConfig) -> None:
    """Run the full extract -> transform -> load -> report pipeline.

    Args:
        config: Pipeline configuration loaded from the environment.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    lines = extract_lines(Path(config.log_file))
    processed = transform_events(lines)
    load_metrics(processed, Path(config.db_path))
    generate_report(processed, Path(REPORT_FILE))
    print(f"Job finished at {datetime.datetime.now()}")


def _write_sample_log(log_path: Path) -> None:
    """Create a small sample log so the pipeline runs standalone.

    Args:
        log_path: Path of the log file to create.
    """
    log_path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
        encoding="utf-8",
    )


def main() -> None:
    """Entry point: load config, seed a missing log, run the pipeline."""
    config = PipelineConfig.from_env()
    log_path = Path(config.log_file)
    if not log_path.exists():
        _write_sample_log(log_path)
    run_pipeline(config)


if __name__ == "__main__":
    main()
