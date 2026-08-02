"""Refactored server-log pipeline: Extract -> Transform -> Load.

Replaces the original ``pipeline.py``:

- All configuration (log path, DB path, DB credentials) comes from
  environment variables instead of module-level constants.
- SQL writes use parameterized queries instead of string formatting,
  removing the SQL-injection surface.
- The single monolithic function is split into extract / transform /
  load stages plus report generation.
- Log lines are parsed with regular expressions instead of split().
- Every function is typed and documented.

The generated ``report.html`` keeps the same information as before:
error summary, API latency table, and active session count.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Log line shape: "YYYY-MM-DD HH:MM:SS LEVEL message"
_LOG_LINE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL)\s+"
    r"(?P<message>.*)$"
)
# INFO payload shapes, matched against the message portion of a log line.
_USER_ACTION_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")
_API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")

_DEFAULT_LOG_FILE = "server.log"
_DEFAULT_DB_PATH = "metrics.db"
_DEFAULT_REPORT_PATH = "report.html"


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration sourced entirely from environment variables.

    ``db_host`` / ``db_port`` / ``db_user`` / ``db_pass`` describe the
    database target and are retained from the original configuration
    surface for a future remote backend; the current SQLite backend
    connects via ``db_path`` only.
    """

    log_path: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: Path


@dataclass(frozen=True)
class LogEvent:
    """A single structured log entry extracted from the log file."""

    dt: str
    kind: str  # "ERROR" | "WARN" | "USER" | "API"
    message: str = ""
    uid: str = ""
    action: str = ""
    endpoint: str = ""
    ms: int = 0


@dataclass(frozen=True)
class ReportData:
    """Aggregated metrics that drive both the DB load and the report."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_session_count: int


def load_config() -> PipelineConfig:
    """Read every configuration value from the environment.

    Paths and the target host/port/user default to the original values so
    the script keeps working without a full env setup; ``DB_PASS`` never
    defaults to a real credential — an empty string forces callers to
    supply it explicitly in production.
    """
    return PipelineConfig(
        log_path=Path(os.getenv("LOG_FILE", _DEFAULT_LOG_FILE)),
        db_path=Path(os.getenv("DB_PATH", _DEFAULT_DB_PATH)),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
        report_path=Path(os.getenv("REPORT_PATH", _DEFAULT_REPORT_PATH)),
    )


def parse_log_line(line: str) -> LogEvent | None:
    """Parse one log line into a structured event.

    Returns ``None`` for malformed lines and for INFO lines that carry
    neither a User nor an API payload (the original ignored those).
    """
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None
    dt = match.group("dt")
    level = match.group("level")
    message = match.group("message")

    if level in ("ERROR", "WARN", "WARNING"):
        return LogEvent(dt=dt, kind=level if level == "ERROR" else "WARN", message=message)

    if level == "INFO":
        user_match = _USER_ACTION_RE.match(message)
        if user_match is not None:
            return LogEvent(
                dt=dt,
                kind="USER",
                uid=user_match.group("uid"),
                action=user_match.group("action"),
            )
        api_match = _API_CALL_RE.match(message)
        if api_match is not None:
            return LogEvent(
                dt=dt,
                kind="API",
                endpoint=api_match.group("endpoint"),
                ms=int(api_match.group("ms") or 0),
            )
    return None


def extract_events(log_path: Path) -> list[LogEvent]:
    """EXTRACT: read the log file and parse every line into events."""
    events: list[LogEvent] = []
    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            event = parse_log_line(line.rstrip("\n"))
            if event is not None:
                events.append(event)
    return events


def transform_events(events: list[LogEvent]) -> ReportData:
    """TRANSFORM: aggregate parsed events into report-ready metrics."""
    error_counts: dict[str, int] = {}
    api_times: dict[str, list[int]] = {}
    active_sessions: set[str] = set()

    for event in events:
        if event.kind == "ERROR":
            error_counts[event.message] = error_counts.get(event.message, 0) + 1
        elif event.kind == "API":
            api_times.setdefault(event.endpoint, []).append(event.ms)
        elif event.kind == "USER":
            if event.action == "logged in":
                active_sessions.add(event.uid)
            elif event.action == "logged out":
                active_sessions.discard(event.uid)

    endpoint_avg_ms = {
        endpoint: sum(times) / len(times) for endpoint, times in api_times.items()
    }
    return ReportData(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_session_count=len(active_sessions),
    )


def load_metrics(db_path: Path, data: ReportData) -> None:
    """LOAD: persist error counts and endpoint latency into SQLite.

    All INSERT statements use ``?`` placeholders; values are never
    interpolated into the SQL text.
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
        now_iso = datetime.datetime.now().isoformat(sep=" ")
        for message, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_iso, message, count),
            )
        for endpoint, avg_ms in data.endpoint_avg_ms.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_iso, endpoint, avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def generate_report(report_path: Path, data: ReportData) -> None:
    """LOAD: write ``report.html`` with the summary, latency, and session info."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in data.error_counts.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    for endpoint, avg_ms in data.endpoint_avg_ms.items():
        lines.append(
            f"<tr><td>{html.escape(endpoint)}</td><td>{avg_ms:.1f}</td></tr>"
        )
    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{data.active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(config: PipelineConfig) -> None:
    """Orchestrate the extract -> transform -> load stages."""
    events = extract_events(config.log_path)
    data = transform_events(events)
    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user} "
        f"(backend: SQLite at {config.db_path})..."
    )
    load_metrics(config.db_path, data)
    generate_report(config.report_path, data)
    print(f"Job finished at {datetime.datetime.now()}")


def main() -> None:
    """Entry point: build config from the environment and run the pipeline."""
    config = load_config()
    if not config.log_path.exists():
        raise FileNotFoundError(
            f"Log file not found: {config.log_path} — set LOG_FILE to a valid path"
        )
    run_pipeline(config)


if __name__ == "__main__":
    main()
