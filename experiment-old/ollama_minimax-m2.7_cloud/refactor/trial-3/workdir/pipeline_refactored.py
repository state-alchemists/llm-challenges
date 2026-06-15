"""
Server log processing pipeline.

Extracts events from server logs, loads them into SQLite, and produces
an HTML report summarizing errors, API latency, and active sessions.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config(NamedTuple):
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """
    Load pipeline configuration from environment variables.

    Returns:
        Config instance with database path, log file path, and credentials.

    Raises:
        ValueError: If required variables are missing.
    """
    db_path = os.getenv("PIPELINE_DB_PATH", "metrics.db")
    log_file = os.getenv("PIPELINE_LOG_FILE", "server.log")
    db_host = os.getenv("PIPELINE_DB_HOST", "localhost")
    db_user = os.getenv("PIPELINE_DB_USER", "admin")
    db_pass = os.getenv("PIPELINE_DB_PASS", "")

    if not db_user:
        raise ValueError("PIPELINE_DB_USER environment variable is required")

    return Config(
        db_path=db_path,
        log_file=log_file,
        db_host=db_host,
        db_port=int(os.getenv("PIPELINE_DB_PORT", "5432")),
        db_user=db_user,
        db_pass=db_pass,
    )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ParsedEvent(NamedTuple):
    """A single parsed log event."""

    timestamp: str
    level: str
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


class ErrorSummary(NamedTuple):
    """Aggregated error count."""

    message: str
    count: int


class ApiMetrics(NamedTuple):
    """Aggregated API latency per endpoint."""

    endpoint: str
    avg_ms: float


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.+)$"
)
ERROR_PATTERN = re.compile(r"(?P<msg>.+)")
WARN_PATTERN = re.compile(r"(?P<msg>.+)")
USER_PATTERN = re.compile(
    r"User (?P<uid>\S+) (?P<action>logged in|logged out)"
)
API_PATTERN = re.compile(
    r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms"
)


def extract_events(log_path: str) -> list[ParsedEvent]:
    """
    Parse log file and yield structured events.

    Args:
        log_path: Path to the server log file.

    Returns:
        List of ParsedEvent objects extracted from the log.
    """
    events: list[ParsedEvent] = []

    if not os.path.exists(log_path):
        return events

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                err_match = ERROR_PATTERN.match(rest)
                if err_match:
                    events.append(
                        ParsedEvent(
                            timestamp=timestamp,
                            level=level,
                            message=err_match.group("msg").strip(),
                        )
                    )

            elif level == "WARN":
                warn_match = WARN_PATTERN.match(rest)
                if warn_match:
                    events.append(
                        ParsedEvent(
                            timestamp=timestamp,
                            level=level,
                            message=warn_match.group("msg").strip(),
                        )
                    )

            elif level == "INFO":
                user_match = USER_PATTERN.match(rest)
                if user_match:
                    events.append(
                        ParsedEvent(
                            timestamp=timestamp,
                            level=level,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = API_PATTERN.match(rest)
                if api_match:
                    events.append(
                        ParsedEvent(
                            timestamp=timestamp,
                            level=level,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("ms")),
                        )
                    )

    return events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_sessions(events: list[ParsedEvent]) -> dict[str, str]:
    """
    Build active session map from user login/logout events.

    Args:
        events: Parsed log events.

    Returns:
        Mapping of user_id -> their last-seen timestamp (still logged in).
    """
    sessions: dict[str, str] = {}

    for event in events:
        if event.level == "INFO" and event.user_id and event.action:
            if event.action == "logged in":
                sessions[event.user_id] = event.timestamp
            elif event.action == "logged out" and event.user_id in sessions:
                del sessions[event.user_id]

    return sessions


def transform_errors(events: list[ParsedEvent]) -> list[ErrorSummary]:
    """
    Aggregate error messages into counts.

    Args:
        events: Parsed log events.

    Returns:
        List of ErrorSummary sorted by count descending.
    """
    counts: dict[str, int] = {}

    for event in events:
        if event.level == "ERROR" and event.message:
            counts[event.message] = counts.get(event.message, 0) + 1

    return sorted(
        [ErrorSummary(msg, cnt) for msg, cnt in counts.items()],
        key=lambda e: e.count,
        reverse=True,
    )


def transform_api_latency(events: list[ParsedEvent]) -> list[ApiMetrics]:
    """
    Compute average latency per API endpoint.

    Args:
        events: Parsed log events.

    Returns:
        List of ApiMetrics sorted alphabetically by endpoint.
    """
    bucket: dict[str, list[int]] = {}

    for event in events:
        if event.level == "INFO" and event.endpoint and event.duration_ms is not None:
            bucket.setdefault(event.endpoint, []).append(event.duration_ms)

    return sorted(
        [
            ApiMetrics(endpoint=ep, avg_ms=sum(ms) / len(ms))
            for ep, ms in bucket.items()
        ],
        key=lambda m: m.endpoint,
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def init_database(conn: sqlite3.Connection) -> None:
    """Create tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_errors(conn: sqlite3.Connection, errors: list[ErrorSummary]) -> None:
    """
    Persist error summaries into the database using parameterized queries.

    Args:
        conn: SQLite connection.
        errors: Aggregated error summaries.
    """
    now = datetime.datetime.now().isoformat()
    for err in errors:
        conn.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, err.message, err.count),
        )


def load_api_metrics(conn: sqlite3.Connection, metrics: list[ApiMetrics]) -> None:
    """
    Persist API latency summaries into the database using parameterized queries.

    Args:
        conn: SQLite connection.
        metrics: Aggregated API metrics.
    """
    now = datetime.datetime.now().isoformat()
    for m in metrics:
        conn.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, m.endpoint, m.avg_ms),
        )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_html_report(
    errors: list[ErrorSummary],
    api_metrics: list[ApiMetrics],
    active_sessions: int,
    output_path: str,
) -> None:
    """
    Write the HTML report to disk.

    Args:
        errors: Error summaries.
        api_metrics: API latency metrics.
        active_sessions: Count of currently active sessions.
        output_path: Destination file path.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err in errors:
        lines.append(
            f"<li><b>{err.message}</b>: {err.count} occurrences</li>"
        )

    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for m in api_metrics:
        lines.append(
            f"<tr><td>{m.endpoint}</td><td>{round(m.avg_ms, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline.

    Loads configuration, extracts events from the log file, transforms
    them into summaries, persists to SQLite, and writes report.html.
    """
    config = load_config()

    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )

    # Extract
    events = extract_events(config.log_file)

    # Transform
    sessions = transform_sessions(events)
    errors = transform_errors(events)
    api_metrics = transform_api_latency(events)

    # Load
    conn = sqlite3.connect(config.db_path)
    try:
        init_database(conn)
        load_errors(conn, errors)
        load_api_metrics(conn, api_metrics)
        conn.commit()
    finally:
        conn.close()

    # Report
    generate_html_report(
        errors=errors,
        api_metrics=api_metrics,
        active_sessions=len(sessions),
        output_path="report.html",
    )

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When run stand-alone, create a sample log so the pipeline has something
    # to process.  In production the log file is provided externally.
    log_file = os.getenv("PIPELINE_LOG_FILE", "server.log")

    if not os.path.exists(log_file):
        sample_log = (
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as fh:
            fh.write(sample_log)

    run_pipeline()
