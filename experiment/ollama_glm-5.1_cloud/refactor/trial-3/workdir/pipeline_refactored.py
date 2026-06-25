"""Server log processing pipeline.

Extracts structured data from server logs, transforms it into aggregated
metrics, loads the results into a SQLite database, and generates an HTML
report.

Configuration is via environment variables (all optional, with defaults):
    PIPELINE_DB_PATH     – SQLite database file path          (default: metrics.db)
    PIPELINE_LOG_FILE    – Server log file path               (default: server.log)
    PIPELINE_REPORT_PATH – HTML report output path            (default: report.html)
    PIPELINE_DB_HOST     – Database host label (informational, default: localhost)
    PIPELINE_DB_PORT     – Database port       (informational, default: 5432)
    PIPELINE_DB_USER     – Database user       (informational, default: admin)
    PIPELINE_DB_PASS     – Database password   (informational, default: password123)

Note: The actual connection is to a local SQLite file (PIPELINE_DB_PATH).
PIPELINE_DB_HOST/PORT/USER/PASS are informational labels printed at startup
and do not affect the database connection.
"""

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Config:
    """Pipeline configuration loaded from environment variables."""

    db_path: Path
    log_file: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Build configuration from environment variables with sensible defaults."""
    return Config(
        db_path=Path(os.environ.get("PIPELINE_DB_PATH", "metrics.db")),
        log_file=Path(os.environ.get("PIPELINE_LOG_FILE", "server.log")),
        report_path=Path(os.environ.get("PIPELINE_REPORT_PATH", "report.html")),
        db_host=os.environ.get("PIPELINE_DB_HOST", "localhost"),
        db_port=int(os.environ.get("PIPELINE_DB_PORT", "5432")),
        db_user=os.environ.get("PIPELINE_DB_USER", "admin"),
        db_pass=os.environ.get("PIPELINE_DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserAction:
    """A user login or logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An API endpoint call with measured latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ExtractedData:
    """Raw events parsed from the log file."""

    error_events: list[ErrorEvent]
    user_actions: list[UserAction]
    api_calls: list[ApiCall]


@dataclass
class PipelineResult:
    """Aggregated metrics ready for database storage and report generation."""

    error_counts: dict[str, int] = field(default_factory=dict)
    endpoint_latencies: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.*)$",
)

_USER_ACTION_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")

_API_CALL_RE = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract: parse log file into structured events
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: Path) -> ExtractedData:
    """Parse the server log file into typed event lists.

    Lines that do not match the expected ``TIMESTAMP LEVEL ...`` format
    are silently skipped.

    Args:
        log_path: Path to the server log file.

    Returns:
        An ``ExtractedData`` containing error events, user actions, and
        API calls.  Returns empty lists when the file does not exist.
    """
    error_events: list[ErrorEvent] = []
    user_actions: list[UserAction] = []
    api_calls: list[ApiCall] = []

    if not log_path.exists():
        return ExtractedData(error_events, user_actions, api_calls)

    with log_path.open("r") as f:
        for line in f:
            match = _LOG_LINE_RE.match(line.rstrip("\n"))
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                error_events.append(
                    ErrorEvent(timestamp=timestamp, message=rest)
                )
                continue

            if level == "INFO":
                user_match = _USER_ACTION_RE.match(rest)
                if user_match:
                    user_actions.append(
                        UserAction(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_CALL_RE.match(rest)
                if api_match:
                    api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration_ms") or "0"),
                        )
                    )

    return ExtractedData(error_events, user_actions, api_calls)


# ---------------------------------------------------------------------------
# Transform: aggregate raw events into metrics
# ---------------------------------------------------------------------------

def transform(data: ExtractedData) -> PipelineResult:
    """Aggregate raw log events into error counts, API latencies, and sessions.

    Args:
        data: The extracted raw events from the log file.

    Returns:
        A ``PipelineResult`` with per-message error counts, per-endpoint
        latency lists, and currently active user sessions.
    """
    result = PipelineResult()

    for event in data.error_events:
        result.error_counts[event.message] = (
            result.error_counts.get(event.message, 0) + 1
        )

    for call in data.api_calls:
        result.endpoint_latencies.setdefault(call.endpoint, []).append(
            call.duration_ms
        )

    for action in data.user_actions:
        if "logged in" in action.action:
            result.active_sessions[action.user_id] = action.timestamp
        elif "logged out" in action.action and action.user_id in result.active_sessions:
            result.active_sessions.pop(action.user_id)

    return result


# ---------------------------------------------------------------------------
# Load: persist metrics to SQLite
# ---------------------------------------------------------------------------

def load_to_database(config: Config, result: PipelineResult) -> None:
    """Insert aggregated metrics into the SQLite database.

    Creates the target tables if they do not already exist.  All INSERT
    statements use parameterized queries to prevent SQL injection.

    Args:
        config: Pipeline configuration (``db_path`` used for the connection).
        result: Aggregated metrics to persist.
    """
    now = str(datetime.datetime.now())

    conn = sqlite3.connect(config.db_path)
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

        for message, count in result.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )

        for endpoint, times in result.endpoint_latencies.items():
            avg_ms = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report: generate HTML report
# ---------------------------------------------------------------------------

def generate_report(result: PipelineResult, report_path: Path) -> None:
    """Write the HTML report with error summary, API latency, and session count.

    All dynamic values are HTML-escaped to prevent injection.

    Args:
        result: Aggregated metrics to render.
        report_path: Destination file path for the report.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for message, count in result.error_counts.items():
        safe_msg = html.escape(message)
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in result.endpoint_latencies.items():
        avg_ms = round(sum(times) / len(times), 1)
        safe_ep = html.escape(endpoint)
        lines.append(f"<tr><td>{safe_ep}</td><td>{avg_ms}</td></tr>")
    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(result.active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with report_path.open("w") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(config: Config) -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    data = extract_log_entries(config.log_file)
    result = transform(data)
    load_to_database(config, result)
    generate_report(result, config.report_path)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = load_config()
    if not config.log_file.exists():
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        config.log_file.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
    run_pipeline(config)