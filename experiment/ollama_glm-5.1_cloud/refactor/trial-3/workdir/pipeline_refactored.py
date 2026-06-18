"""Refactored server-log pipeline following an Extract → Transform → Load pattern.

Reads server logs, aggregates error counts, API latency, and active sessions,
persists the results to SQLite, and generates an HTML report.

All configuration is sourced from environment variables with sensible
defaults so the script works out of the box in development:

  PIPELINE_DB_PATH   – SQLite database file  (default: metrics.db)
  PIPELINE_LOG_FILE  – Log file path         (default: server.log)
  PIPELINE_DB_HOST   – Database host         (default: localhost)
  PIPELINE_DB_PORT   – Database port         (default: 5432)
  PIPELINE_DB_USER   – Database user         (default: admin)
  PIPELINE_DB_PASS   – Database password    (default: empty; set in production)
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Runtime configuration, fully driven by environment variables."""

    db_path: Path
    log_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Build configuration from environment variables.

        Every value has a default so the script runs without any env-vars
        set, but credentials should always be provided via the environment
        in production deployments.
        """
        return cls(
            db_path=Path(os.getenv("PIPELINE_DB_PATH", "metrics.db")),
            log_file=Path(os.getenv("PIPELINE_LOG_FILE", "server.log")),
            db_host=os.getenv("PIPELINE_DB_HOST", "localhost"),
            db_port=int(os.getenv("PIPELINE_DB_PORT", "5432")),
            db_user=os.getenv("PIPELINE_DB_USER", "admin"),
            db_pass=os.getenv("PIPELINE_DB_PASS", ""),
        )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEntry:
    """A parsed INFO User-event log line."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEntry:
    """A parsed INFO API-call log line."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


LogEntry = ErrorEntry | UserEntry | ApiEntry | WarnEntry


@dataclass
class AggregatedMetrics:
    """Report-ready aggregates produced by the transform step."""

    error_counts: dict[str, int] = field(default_factory=dict)
    api_latency: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extract – regex-based log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s+(?P<level>ERROR|INFO|WARN)"
    r"\s+(?P<payload>.*)$"
)

_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$")


def _parse_line(line: str) -> LogEntry | None:
    """Parse a single log line into a typed entry, or *None* if unrecognised."""
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    payload = match.group("payload")

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, message=payload.strip())

    if level == "WARN":
        return WarnEntry(timestamp=timestamp, message=payload.strip())

    # INFO lines – distinguish User events from API calls by payload pattern
    if level == "INFO":
        user_match = _USER_RE.match(payload)
        if user_match is not None:
            return UserEntry(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action").strip(),
            )

        api_match = _API_RE.match(payload)
        if api_match is not None:
            return ApiEntry(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("duration")),
            )

    return None


def extract(log_file: Path) -> list[LogEntry]:
    """Read *log_file* and return a list of parsed, typed entries.

    Returns an empty list if the file does not exist.
    """
    if not log_file.exists():
        return []

    entries: list[LogEntry] = []
    with log_file.open() as fh:
        for line in fh:
            entry = _parse_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform – aggregate into report-ready metrics
# ---------------------------------------------------------------------------


def transform(entries: list[LogEntry]) -> AggregatedMetrics:
    """Aggregate raw entries into error counts, API latency, and active sessions."""
    metrics = AggregatedMetrics()

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            metrics.error_counts[entry.message] = (
                metrics.error_counts.get(entry.message, 0) + 1
            )

        elif isinstance(entry, UserEntry):
            if "logged in" in entry.action:
                metrics.active_sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in metrics.active_sessions:
                del metrics.active_sessions[entry.user_id]

        elif isinstance(entry, ApiEntry):
            metrics.api_latency.setdefault(entry.endpoint, []).append(
                entry.duration_ms
            )

    return metrics


# ---------------------------------------------------------------------------
# Load – persist to database and generate HTML report
# ---------------------------------------------------------------------------


def _init_db(conn: sqlite3.Connection) -> None:
    """Create pipeline tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def _persist_metrics(
    conn: sqlite3.Connection,
    metrics: AggregatedMetrics,
    now: str,
) -> None:
    """Insert aggregated metrics using parameterised queries (no SQL injection)."""
    for message, count in metrics.error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in metrics.api_latency.items():
        avg_ms = sum(times) / len(times)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )


def _render_html(metrics: AggregatedMetrics) -> str:
    """Build the HTML report from aggregated metrics."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in metrics.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in metrics.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(metrics.active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def load(
    config: PipelineConfig,
    metrics: AggregatedMetrics,
    now: str,
    report_path: Path = Path("report.html"),
) -> None:
    """Persist metrics to SQLite and write the HTML report.

    Args:
        config: Pipeline configuration (DB path, credentials, etc.).
        metrics: Aggregated metrics from the transform step.
        now: Timestamp string used for DB inserts.
        report_path: Output path for the HTML report.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    with sqlite3.connect(config.db_path) as conn:
        _init_db(conn)
        _persist_metrics(conn, metrics, now)
        conn.commit()

    report_path.write_text(_render_html(metrics))

    print(f"Job finished at {now}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_SAMPLE_LOG_LINES = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


def _ensure_sample_log(log_file: Path) -> None:
    """Create a minimal sample log file if one does not already exist."""
    if not log_file.exists():
        log_file.write_text(_SAMPLE_LOG_LINES)


def run_pipeline() -> None:
    """End-to-end pipeline: extract → transform → load."""
    config = PipelineConfig.from_env()
    now = str(datetime.now())

    _ensure_sample_log(config.log_file)
    entries = extract(config.log_file)
    metrics = transform(entries)
    load(config, metrics, now)


if __name__ == "__main__":
    run_pipeline()