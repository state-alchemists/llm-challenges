"""Server-log pipeline: Extract → Transform → Load.

Parses server logs, computes error summaries and API latency metrics,
persists results to SQLite, and generates an HTML report.

Configuration is read from environment variables with sensible defaults.
"""

from __future__ import annotations

import datetime
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
    """Runtime configuration sourced from environment variables."""

    db_path: Path
    log_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: Path


def load_config() -> Config:
    """Build a :class:`Config` from environment variables.

    Environment variables and defaults:

    * ``LOG_DB_PATH``       – SQLite database path       (default: ``metrics.db``)
    * ``LOG_FILE_PATH``     – Server log file path        (default: ``server.log``)
    * ``DB_HOST``           – Database host               (default: ``localhost``)
    * ``DB_PORT``           – Database port                (default: ``5432``)
    * ``DB_USER``           – Database user                (default: ``admin``)
    * ``DB_PASS``           – Database password           (default: empty)
    * ``REPORT_PATH``       – HTML report output path      (default: ``report.html``)
    """
    return Config(
        db_path=Path(os.environ.get("LOG_DB_PATH", "metrics.db")),
        log_file=Path(os.environ.get("LOG_FILE_PATH", "server.log")),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_user=os.environ.get("DB_USER", "admin"),
        db_pass=os.environ.get("DB_PASS", ""),
        report_path=Path(os.environ.get("REPORT_PATH", "report.html")),
    )


# ---------------------------------------------------------------------------
# Parsed log entries
# ---------------------------------------------------------------------------

# Top-level log-line pattern: "2024-01-01 12:05:00 ERROR ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<message>.*)$"
)

# User-event pattern inside an INFO message: "User 42 logged in"
_USER_EVENT_RE = re.compile(
    r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$"
)

# API-call pattern inside an INFO message: "API /users/profile took 250ms"
_API_CALL_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration_ms>\d+)ms)?$"
)


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """An ERROR-level log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An API call with its latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarningEntry:
    """A WARN-level log line."""

    timestamp: str
    message: str


# Union type for all parsed entries
ParsedEntry = ErrorEntry | UserEvent | ApiCall | WarningEntry


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> ParsedEntry | None:
    """Parse a single log line into a structured entry.

    Returns ``None`` for lines that do not match any known pattern.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, message=message)

    if level == "WARN":
        return WarningEntry(timestamp=timestamp, message=message)

    # INFO lines — check for user events and API calls
    if level == "INFO":
        user_match = _USER_EVENT_RE.match(message)
        if user_match:
            return UserEvent(
                timestamp=timestamp,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )

        api_match = _API_CALL_RE.match(message)
        if api_match:
            return ApiCall(
                timestamp=timestamp,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("duration_ms") or 0),
            )

    return None


def extract(log_path: Path) -> list[ParsedEntry]:
    """Read the log file and return a list of parsed entries.

    Silently skips lines that do not match any known pattern.
    Raises :class:`FileNotFoundError` if the log file does not exist.
    """
    entries: list[ParsedEntry] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@dataclass
class ReportData:
    """Aggregated data ready for reporting and persistence."""

    error_summary: dict[str, int] = field(default_factory=dict)
    api_latency: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: int = 0


def transform(entries: list[ParsedEntry]) -> ReportData:
    """Compute error counts, API latency averages, and active-session count."""
    error_counts: dict[str, int] = {}
    api_latency: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, ApiCall):
            api_latency.setdefault(entry.endpoint, []).append(entry.duration_ms)

        elif isinstance(entry, UserEvent):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)

    return ReportData(
        error_summary=error_counts,
        api_latency=api_latency,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(db_path: Path, report: ReportData, now: str) -> None:
    """Persist error counts and API latency averages to SQLite.

    Uses parameterized queries to prevent SQL injection.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in report.error_summary.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in report.api_latency.items():
            avg_ms = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(report: ReportData, output_path: Path) -> None:
    """Write the HTML report to *output_path*.

    The report contains three sections matching the original output:
    error summary, API latency table, and active-session count.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in report.error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in report.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{report.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline(config: Config | None = None) -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Uses *config* (or the default from :func:`load_config`) for all paths
    and credentials.
    """
    if config is None:
        config = load_config()

    # Extract
    entries = extract(config.log_file)
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    # Transform
    report = transform(entries)

    # Load
    now = str(datetime.datetime.now())
    load_to_database(config.db_path, report, now)
    generate_report(report, config.report_path)

    print(f"Job finished at {now}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    config = load_config()

    # Create a sample log file if none exists (mirrors original bootstrap).
    if not config.log_file.exists():
        config.log_file.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )

    run_pipeline(config)