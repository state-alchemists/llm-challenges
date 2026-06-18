"""Refactored server-log pipeline: Extract → Transform → Load.

Reads server logs, computes error summaries and API latency statistics,
persists metrics to SQLite, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — all values sourced from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """Base record for a parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass
class ErrorRecord(LogEntry):
    """An ERROR-level log entry."""


@dataclass
class UserRecord(LogEntry):
    """An INFO User log entry (login / logout events)."""

    user_id: str
    action: str


@dataclass
class ApiCallRecord(LogEntry):
    """An INFO API log entry with endpoint and latency."""

    endpoint: str
    latency_ms: int


@dataclass
class WarnRecord(LogEntry):
    """A WARN-level log entry."""


@dataclass
class PipelineResult:
    """Aggregated metrics ready for persistence and reporting."""

    error_counts: dict[str, int] = field(default_factory=dict)
    endpoint_latency: dict[str, list[int]] = field(default_factory=dict)
    active_session_count: int = 0


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<rest>.+)$"
)

_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<latency>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract — read and parse the log file
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: str) -> list[LogEntry]:
    """Parse the server log file into structured records.

    Uses regex to robustly match timestamp, level, and the remainder of
    each line, then dispatches to specialised sub-patterns for User and
    API entries.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A list of :class:`LogEntry` subclass instances.
    """
    entries: list[LogEntry] = []
    path = Path(log_path)
    if not path.is_file():
        print(f"Log file not found: {log_path}")
        return entries

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                entries.append(
                    ErrorRecord(timestamp=timestamp, level=level, message=rest)
                )
            elif level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    entries.append(
                        UserRecord(
                            timestamp=timestamp,
                            level=level,
                            message=rest,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    entries.append(
                        ApiCallRecord(
                            timestamp=timestamp,
                            level=level,
                            message=rest,
                            endpoint=api_match.group("endpoint"),
                            latency_ms=int(api_match.group("latency")),
                        )
                    )
            elif level == "WARN":
                entries.append(
                    WarnRecord(timestamp=timestamp, level=level, message=rest)
                )

    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate parsed entries into summary statistics
# ---------------------------------------------------------------------------


def transform_entries(entries: list[LogEntry]) -> PipelineResult:
    """Aggregate parsed log entries into summary metrics.

    Computes error-message frequency, per-endpoint API latency lists,
    and the current count of active (logged-in) user sessions.

    Args:
        entries: Parsed log entries from :func:`extract_log_entries`.

    Returns:
        A :class:`PipelineResult` with aggregated metrics.
    """
    error_counts: dict[str, int] = {}
    endpoint_latency: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorRecord):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, UserRecord):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action:
                sessions.pop(entry.user_id, None)

        elif isinstance(entry, ApiCallRecord):
            endpoint_latency.setdefault(entry.endpoint, []).append(entry.latency_ms)

    return PipelineResult(
        error_counts=error_counts,
        endpoint_latency=endpoint_latency,
        active_session_count=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — persist to database and generate HTML report
# ---------------------------------------------------------------------------


def load_to_database(result: PipelineResult, db_path: str) -> None:
    """Persist aggregated metrics into a SQLite database.

    Creates tables if they do not exist, then inserts error counts and
    average API latencies using parameterized queries (no string
    interpolation — safe from SQL injection).

    Args:
        result: Aggregated pipeline results.
        db_path: Path to the SQLite database file.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
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

        now = str(datetime.datetime.now())
        for msg, count in result.error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in result.endpoint_latency.items():
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_report(
    result: PipelineResult, output_path: str = "report.html"
) -> None:
    """Generate an HTML report from aggregated pipeline results.

    The report includes an error summary, an API latency table, and
    the active-session count.

    Args:
        result: Aggregated pipeline results.
        output_path: File path for the generated HTML report.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in result.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in result.endpoint_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{result.active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    entries = extract_log_entries(LOG_FILE)
    result = transform_entries(entries)
    load_to_database(result, DB_PATH)
    load_report(result)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not Path(LOG_FILE).is_file():
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    run_pipeline()