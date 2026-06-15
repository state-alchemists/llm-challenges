"""Log processing pipeline: extract, transform, and load server log data.

Usage:
    export LOG_PATH=server.log
    export DB_PATH=metrics.db
    python pipeline_refactored.py

If LOG_PATH does not exist, sample data is created and the pipeline runs
against it.
"""

import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ─── Configuration ───────────────────────────────────────────────────────────

_ENV_LOG_PATH = "LOG_PATH"
_ENV_DB_PATH = "DB_PATH"

_DEFAULT_LOG_PATH = "server.log"
_DEFAULT_DB_PATH = "metrics.db"

LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN|DEBUG) "
    r"(?P<message>.+)$"
)
USER_PATTERN = re.compile(r"^User (\S+) (.+)$")
API_PATTERN = re.compile(r"^API (\S+) took (\d+)ms$")


@dataclass(frozen=True)
class Config:
    """Immutable application configuration sourced from environment variables.

    Attributes:
        log_path: Path to the server log file.
        db_path: Path to the SQLite database file.
    """

    log_path: Path
    db_path: Path

    @classmethod
    def from_env(cls) -> "Config":
        """Build Config from environment variables, falling back to defaults."""
        return cls(
            log_path=Path(os.getenv(_ENV_LOG_PATH, _DEFAULT_LOG_PATH)),
            db_path=Path(os.getenv(_ENV_DB_PATH, _DEFAULT_DB_PATH)),
        )


# ─── Data Types ──────────────────────────────────────────────────────────────


@dataclass
class LogEvent:
    """A single parsed log entry.

    Attributes:
        timestamp: Log line timestamp string.
        level: Log level (ERROR, INFO, WARN, DEBUG).
        message: Raw message portion of the log line.
        event_type: Structured category (error, user_action, api_call, warning).
        user_id: Extracted user ID for user_action events.
        action: Extracted action description for user_action events.
        endpoint: API endpoint path for api_call events.
        duration_ms: API response duration in milliseconds for api_call events.
    """

    timestamp: str
    level: str
    message: str
    event_type: str = "log"
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ─── Extract ─────────────────────────────────────────────────────────────────


def parse_log_line(line: str) -> LogEvent | None:
    """Parse a single server log line into a structured LogEvent.

    Supports four log patterns, identified by level and message content:

    * ``ERROR <message>`` — yields ``event_type="error"``.
    * ``INFO User <id> <action>`` — yields ``event_type="user_action"``
      with ``user_id`` and ``action``. Login/logout semantics are handled
      downstream in the transform phase — no session state here.
    * ``INFO API <endpoint> took <N>ms`` — yields ``event_type="api_call"``
      with ``endpoint`` and ``duration_ms``.
    * ``WARN <message>`` — yields ``event_type="warning"``.
    * Anything else — yields ``event_type="log"`` with no extra fields.

    Returns None if the line does not match the expected timestamp + level
    prefix.
    """
    match = LINE_PATTERN.match(line.strip())
    if not match:
        return None

    ts = match.group("timestamp")
    level = match.group("level")
    msg = match.group("message")

    if level == "ERROR":
        return LogEvent(ts, level, msg, event_type="error")

    if level == "INFO":
        user_match = USER_PATTERN.match(msg)
        if user_match:
            return LogEvent(
                ts,
                level,
                msg,
                event_type="user_action",
                user_id=user_match.group(1),
                action=user_match.group(2),
            )
        api_match = API_PATTERN.match(msg)
        if api_match:
            return LogEvent(
                ts,
                level,
                msg,
                event_type="api_call",
                endpoint=api_match.group(1),
                duration_ms=int(api_match.group(2)),
            )
        return LogEvent(ts, level, msg, event_type="log")

    if level == "WARN":
        return LogEvent(ts, level, msg, event_type="warning")

    return LogEvent(ts, level, msg, event_type="log")


def extract_logs(log_path: Path) -> list[LogEvent]:
    """Read and parse all log entries from *log_path*.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of parsed LogEvent objects. Lines that fail to match the
        expected format are silently skipped.
    """
    events: list[LogEvent] = []
    if not log_path.is_file():
        return events
    with log_path.open() as f:
        for line in f:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)
    return events


# ─── Transform ───────────────────────────────────────────────────────────────


def aggregate_errors(events: list[LogEvent]) -> dict[str, int]:
    """Count occurrences of each unique error message.

    Args:
        events: Parsed log events.

    Returns:
        Mapping of error message text to occurrence count.
    """
    counts: dict[str, int] = {}
    for e in events:
        if e.event_type == "error":
            counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def compute_api_latency(events: list[LogEvent]) -> dict[str, list[int]]:
    """Group API call durations by endpoint.

    Args:
        events: Parsed log events.

    Returns:
        Mapping of endpoint path to list of observed durations in
        milliseconds.
    """
    stats: dict[str, list[int]] = defaultdict(list)
    for e in events:
        if e.event_type == "api_call" and e.endpoint is not None and e.duration_ms is not None:
            stats[e.endpoint].append(e.duration_ms)
    return dict(stats)


def track_active_sessions(events: list[LogEvent]) -> set[str]:
    """Determine which user sessions are still active at end of log.

    Tracks login/logout events. A user is active if they logged in but did
    not subsequently log out.

    Args:
        events: Parsed log events.

    Returns:
        Set of user IDs with active sessions.
    """
    active: set[str] = set()
    for e in events:
        if e.event_type != "user_action" or e.user_id is None or e.action is None:
            continue
        if "logged in" in e.action:
            active.add(e.user_id)
        elif "logged out" in e.action:
            active.discard(e.user_id)
    return active


# ─── Load (Database) ─────────────────────────────────────────────────────────


def _init_database(db_path: Path) -> sqlite3.Connection:
    """Open or create the SQLite database and ensure tables exist.

    Args:
        db_path: Path to the database file.

    Returns:
        An open connection (caller must close).
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors ("
        "  dt TEXT, message TEXT, count INTEGER"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics ("
        "  dt TEXT, endpoint TEXT, avg_ms REAL"
        ")"
    )
    return conn


def _write_error_summary(
    conn: sqlite3.Connection, error_counts: dict[str, int]
) -> None:
    """Insert error summary records using a parameterized query.

    Args:
        conn: Open database connection.
        error_counts: Mapping of error message to occurrence count.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, count) for msg, count in error_counts.items()],
    )


def _write_api_metrics(
    conn: sqlite3.Connection, api_latency: dict[str, list[int]]
) -> None:
    """Insert API latency averages using a parameterized query.

    Args:
        conn: Open database connection.
        api_latency: Mapping of endpoint to list of duration measurements.
    """
    now = datetime.now(timezone.utc).isoformat()
    averages = [
        (now, endpoint, round(sum(times) / len(times), 1))
        for endpoint, times in api_latency.items()
        if times
    ]
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        averages,
    )


def _load_database(
    conn: sqlite3.Connection,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """Write all computed metrics to the database.

    Args:
        conn: Open database connection.
        error_counts: Mapping of error message to occurrence count.
        api_latency: Mapping of endpoint to list of duration measurements.
    """
    _write_error_summary(conn, error_counts)
    _write_api_metrics(conn, api_latency)
    conn.commit()


# ─── Load (Report) ───────────────────────────────────────────────────────────


def _generate_report_html(
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: set[str],
) -> str:
    """Build the HTML report string.

    Args:
        error_counts: Mapping of error message to occurrence count.
        api_latency: Mapping of endpoint to list of duration measurements.
        active_sessions: Set of user IDs with active sessions.

    Returns:
        Complete HTML document as a string.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def _write_report(html: str, output_path: Path) -> None:
    """Write the HTML report to *output_path*.

    Args:
        html: Complete HTML document string.
        output_path: Destination file path.
    """
    output_path.write_text(html)


# ─── Pipeline Orchestrator ───────────────────────────────────────────────────


def run_pipeline(config: Config) -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Steps:
    1. Extract: read and parse log entries from *config.log_path*.
    2. Transform: aggregate errors, compute API latency, track sessions.
    3. Load: persist to database (parameterized queries) and render HTML
       report.

    Args:
        config: Application configuration with log and DB paths.
    """
    events = extract_logs(config.log_path)
    error_counts = aggregate_errors(events)
    api_latency = compute_api_latency(events)
    active_sessions = track_active_sessions(events)

    conn = _init_database(config.db_path)
    try:
        _load_database(conn, error_counts, api_latency)
    finally:
        conn.close()

    html = _generate_report_html(error_counts, api_latency, active_sessions)
    _write_report(html, Path("report.html"))


# ─── Entry Point ─────────────────────────────────────────────────────────────


def _create_sample_log(log_path: Path) -> None:
    """Write sample log data to *log_path* for demonstration.

    Args:
        log_path: Destination file path.
    """
    log_path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )


if __name__ == "__main__":
    config = Config.from_env()
    if not config.log_path.is_file():
        _create_sample_log(config.log_path)
    run_pipeline(config)
