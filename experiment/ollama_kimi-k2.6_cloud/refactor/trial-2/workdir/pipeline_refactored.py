"""Refactored pipeline: extract server logs, transform metrics, load to DB and HTML report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: str

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables with sensible defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
            report_path=os.getenv("REPORT_PATH", "report.html"),
        )


# Regex patterns for log parsing
_LINE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<rest>.*)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<dur>\d+)ms)?")


@dataclass(frozen=True, slots=True)
class LogEvent:
    """Base class for parsed log events."""

    dt: str


@dataclass(frozen=True, slots=True)
class ErrorEvent(LogEvent):
    """Server error log entry."""

    message: str


@dataclass(frozen=True, slots=True)
class WarnEvent(LogEvent):
    """Server warning log entry."""

    message: str


@dataclass(frozen=True, slots=True)
class UserEvent(LogEvent):
    """User session activity log entry."""

    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEvent(LogEvent):
    """API call latency log entry."""

    endpoint: str
    duration_ms: int


def parse_line(line: str) -> LogEvent | None:
    """Parse a single log line into a typed event using regex.

    Expected format::

        YYYY-MM-DD HH:MM:SS LEVEL message...

    Returns ``None`` if the line does not match the expected format.
    """
    m = _LINE_RE.match(line.strip())
    if not m:
        return None

    dt = m.group("dt")
    level = m.group("level")
    rest = m.group("rest")

    if level == "ERROR":
        return ErrorEvent(dt=dt, message=rest)
    if level == "WARN":
        return WarnEvent(dt=dt, message=rest)
    if level == "INFO":
        um = _USER_RE.match(rest)
        if um:
            return UserEvent(dt=dt, user_id=um.group("uid"), action=um.group("action"))
        am = _API_RE.match(rest)
        if am:
            dur = int(am.group("dur")) if am.group("dur") is not None else 0
            return ApiEvent(dt=dt, endpoint=am.group("endpoint"), duration_ms=dur)
    return None


def extract(log_file: str) -> list[LogEvent]:
    """Extract and parse log events from the given log file.

    Returns a list of typed log events. Lines that fail parsing are silently
    dropped.
    """
    events: list[LogEvent] = []
    path = Path(log_file).expanduser()
    if not path.exists():
        return events

    with path.open("r") as fh:
        for line in fh:
            event = parse_line(line)
            if event is not None:
                events.append(event)
    return events


def transform(
    events: list[LogEvent],
) -> tuple[dict[str, int], dict[str, float], dict[str, str]]:
    """Transform raw log events into aggregated metrics.

    Returns:
        - ``error_counts``: mapping of error message to occurrence count.
        - ``api_averages``: mapping of endpoint to average latency in ms.
        - ``active_sessions``: mapping of user id to login datetime.
    """
    error_counts: dict[str, int] = {}
    api_times: dict[str, list[int]] = defaultdict(list)
    active_sessions: dict[str, str] = {}

    for event in events:
        if isinstance(event, ErrorEvent):
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
        elif isinstance(event, ApiEvent):
            api_times[event.endpoint].append(event.duration_ms)
        elif isinstance(event, UserEvent):
            if "logged in" in event.action:
                active_sessions[event.user_id] = event.dt
            elif "logged out" in event.action and event.user_id in active_sessions:
                active_sessions.pop(event.user_id)

    api_averages = {ep: sum(times) / len(times) for ep, times in api_times.items()}
    return error_counts, api_averages, active_sessions


def load(
    config: Config,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    active_sessions: dict[str, str],
) -> None:
    """Load aggregated metrics into SQLite and generate an HTML report.

    Args:
        config: Runtime configuration.
        error_counts: Aggregated error counts.
        api_averages: Aggregated API latency averages.
        active_sessions: Currently active user sessions.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    with closing(sqlite3.connect(config.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg in api_averages.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()

    _write_report(config.report_path, error_counts, api_averages, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


def _write_report(
    report_path: str,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    active_sessions: dict[str, str],
) -> None:
    """Generate ``report.html`` with error summary, API latency, and active sessions.

    The output structure mirrors the original report for backward compatibility.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w") as fh:
        fh.write(out)


def _ensure_sample_log(log_file: str) -> None:
    """Create a sample ``server.log`` if one does not already exist."""
    log_path = Path(log_file)
    if log_path.exists():
        return
    with log_path.open("w") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


def main() -> None:
    """Pipeline entrypoint."""
    config = Config.from_env()
    _ensure_sample_log(config.log_file)
    events = extract(config.log_file)
    error_counts, api_averages, active_sessions = transform(events)
    load(config, error_counts, api_averages, active_sessions)


if __name__ == "__main__":
    main()
