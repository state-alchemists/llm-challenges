"""Server-log processing pipeline: Extract → Transform → Load.

Reads a server log file, parses structured events, aggregates metrics,
persists them to SQLite, and generates an HTML report.

Configuration is provided via environment variables (with defaults):
    LOG_FILE_PATH   – Path to the server log file (default: server.log)
    DB_PATH         – Path to the SQLite database file (default: metrics.db)
    DB_HOST         – Database host label, used for display only (default: localhost)
    DB_PORT         – Database port label, used for display only (default: 5432)
    DB_USER         – Database user label, used for display only (default: admin)
    DB_PASS         – Database password (default: empty; prefer secrets management)
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Counter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE_PATH = Path(os.environ.get("LOG_FILE_PATH", "server.log"))
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "")

REPORT_PATH = Path(os.environ.get("REPORT_PATH", "report.html"))

# ---------------------------------------------------------------------------
# Compiled regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# Example: "2024-01-01 12:05:00 ERROR Database timeout"
_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+ERROR\s+(?P<message>.+)$"
)

# Example: "2024-01-01 12:00:00 INFO User 42 logged in"
_RE_USER_EVENT = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+User\s+(?P<user_id>\S+)\s+(?P<action>.+)$"
)

# Example: "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
_RE_API_CALL = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration_ms>\d+)ms$"
)

# Example: "2024-01-01 12:09:00 WARN Memory usage at 87%"
_RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+WARN\s+(?P<message>.+)$"
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
class UserEvent:
    """An INFO User log entry (login or logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An INFO API log entry with latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnEvent:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class PipelineResult:
    """Aggregated output of the transform step."""

    error_counts: Counter[str] = field(default_factory=Counter)
    api_latency: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)
    warnings: list[WarnEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract: read raw log lines
# ---------------------------------------------------------------------------


def extract_lines(log_path: Path) -> list[str]:
    """Read the log file and return all non-empty lines.

    Args:
        log_path: Path to the server log file.

    Returns:
        List of stripped, non-empty lines from the log file.
        Returns an empty list if the file does not exist.
    """
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return []
    with log_path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Transform: parse lines into structured events
# ---------------------------------------------------------------------------


def parse_line(line: str) -> ErrorEvent | UserEvent | ApiCall | WarnEvent | None:
    """Parse a single log line into a typed event.

    Uses compiled regex patterns to match known log formats.
    Returns ``None`` for lines that don't match any known pattern.

    Args:
        line: A single stripped log line.

    Returns:
        A parsed event dataclass, or ``None`` if the line is unrecognized.
    """
    if match := _RE_ERROR.match(line):
        return ErrorEvent(timestamp=match.group("timestamp"), message=match.group("message"))

    if match := _RE_API_CALL.match(line):
        return ApiCall(
            timestamp=match.group("timestamp"),
            endpoint=match.group("endpoint"),
            duration_ms=int(match.group("duration_ms")),
        )

    if match := _RE_USER_EVENT.match(line):
        return UserEvent(
            timestamp=match.group("timestamp"),
            user_id=match.group("user_id"),
            action=match.group("action"),
        )

    if match := _RE_WARN.match(line):
        return WarnEvent(timestamp=match.group("timestamp"), message=match.group("message"))

    return None


def transform(lines: list[str]) -> PipelineResult:
    """Parse log lines and aggregate into metrics.

    Args:
        lines: Raw log lines (as returned by :func:`extract_lines`).

    Returns:
        A :class:`PipelineResult` with error counts, API latency data,
        active sessions, and warnings.
    """
    result = PipelineResult()

    for line in lines:
        event = parse_line(line)
        if event is None:
            continue

        if isinstance(event, ErrorEvent):
            result.error_counts[event.message] += 1

        elif isinstance(event, UserEvent):
            if "logged in" in event.action:
                result.active_sessions[event.user_id] = event.timestamp
            elif "logged out" in event.action:
                result.active_sessions.pop(event.user_id, None)

        elif isinstance(event, ApiCall):
            result.api_latency.setdefault(event.endpoint, []).append(event.duration_ms)

        elif isinstance(event, WarnEvent):
            result.warnings.append(event)

    return result


# ---------------------------------------------------------------------------
# Load: persist to database and generate report
# ---------------------------------------------------------------------------


def load_to_database(db_path: str, result: PipelineResult) -> None:
    """Insert aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        result: Aggregated pipeline results to persist.
    """
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in result.error_counts.items():
            cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

        for endpoint, times in result.api_latency.items():
            avg_ms = sum(times) / len(times)
            cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, endpoint, avg_ms))

        conn.commit()
    finally:
        conn.close()


def generate_report(result: PipelineResult) -> str:
    """Build an HTML report from aggregated metrics.

    All dynamic values are HTML-escaped to prevent injection.

    Args:
        result: Aggregated pipeline results.

    Returns:
        Complete HTML document as a string.
    """
    parts: list[str] = []
    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")
    parts.append("<h1>Error Summary</h1>")
    parts.append("<ul>")
    for msg, count in result.error_counts.items():
        parts.append(f"<li><b>{html.escape(msg)}</b>: {count} occurrences</li>")
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in result.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        parts.append(f"<tr><td>{html.escape(endpoint)}</td><td>{avg}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{len(result.active_sessions)} user(s) currently active</p>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def load(db_path: str, report_path: Path, result: PipelineResult) -> None:
    """Persist results to the database and write the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        report_path: Destination path for the HTML report.
        result: Aggregated pipeline results.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    load_to_database(db_path, result)

    report_html = generate_report(result)
    report_path.write_text(report_html, encoding="utf-8")

    print(f"Job finished at {datetime.now()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    lines = extract_lines(LOG_FILE_PATH)
    result = transform(lines)
    load(DB_PATH, REPORT_PATH, result)


if __name__ == "__main__":
    # Seed a sample log file when none exists, matching original behaviour.
    if not LOG_FILE_PATH.exists():
        LOG_FILE_PATH.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    run_pipeline()