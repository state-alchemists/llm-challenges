"""Refactored server-log pipeline: extract, transform, load, and report.

Reads server logs, parses structured entries via regex, persists metrics
to SQLite with parameterized queries, and generates an HTML report.

All configuration (database path, log file, credentials) is sourced
from environment variables.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
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

@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """An ERROR-level log event."""
    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class ApiCallEntry:
    """An API latency measurement from an INFO log line."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """A WARN-level log event."""
    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserSessionEntry:
    """A user login/logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ParsedLog:
    """Aggregated result of log transformation."""
    errors: list[ErrorEntry] = field(default_factory=list)
    api_calls: list[ApiCallEntry] = field(default_factory=list)
    warnings: list[WarnEntry] = field(default_factory=list)
    user_events: list[UserSessionEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns for log parsing
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<msg>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_RE_API = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)
_RE_WARN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<msg>.+)$"
)


# ---------------------------------------------------------------------------
# Extract: read raw log lines
# ---------------------------------------------------------------------------

def extract_log_lines(log_path: str) -> list[str]:
    """Read the log file and return all non-empty lines.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of stripped, non-empty lines from the log.
    """
    path = Path(log_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Transform: parse log lines into structured data
# ---------------------------------------------------------------------------

def transform_log_entries(lines: list[str]) -> ParsedLog:
    """Parse raw log lines into structured, typed entries using regex.

    Args:
        lines: Raw log lines (from :func:`extract_log_lines`).

    Returns:
        A :class:`ParsedLog` containing categorized entries.
    """
    parsed = ParsedLog()
    for line in lines:
        if m := _RE_ERROR.match(line):
            parsed.errors.append(
                ErrorEntry(timestamp=m["ts"], message=m["msg"])
            )
        elif m := _RE_USER.match(line):
            parsed.user_events.append(
                UserSessionEntry(
                    timestamp=m["ts"], user_id=m["uid"], action=m["action"]
                )
            )
        elif m := _RE_API.match(line):
            parsed.api_calls.append(
                ApiCallEntry(
                    timestamp=m["ts"],
                    endpoint=m["endpoint"],
                    latency_ms=int(m["ms"]),
                )
            )
        elif m := _RE_WARN.match(line):
            parsed.warnings.append(
                WarnEntry(timestamp=m["ts"], message=m["msg"])
            )
    return parsed


def aggregate_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Count occurrences of each distinct error message.

    Args:
        errors: List of error entries.

    Returns:
        A mapping from error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def aggregate_api_latency(api_calls: list[ApiCallEntry]) -> dict[str, list[int]]:
    """Group API latencies by endpoint.

    Args:
        api_calls: List of API call entries with latency data.

    Returns:
        A mapping from endpoint to a list of latency measurements (ms).
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.latency_ms)
    return stats


def count_active_sessions(user_events: list[UserSessionEntry]) -> int:
    """Compute the number of currently active sessions.

    A session is active if the user logged in but has not yet logged out.

    Args:
        user_events: Ordered list of user login/logout events.

    Returns:
        The count of users with an open session.
    """
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return len(sessions)


# ---------------------------------------------------------------------------
# Load: persist to SQLite
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """Persist aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Error message to occurrence count mapping.
        api_stats: Endpoint to latency list mapping.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.now().isoformat()
    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_stats.items():
        avg_ms = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report: generate HTML
# ---------------------------------------------------------------------------

def generate_report(
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Produce an HTML report summarizing errors, API latency, and sessions.

    Args:
        error_counts: Error message to occurrence count mapping.
        api_stats: Endpoint to latency list mapping.
        active_sessions: Number of currently active user sessions.
        output_path: Destination file path for the HTML report.
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
    for endpoint, times in api_stats.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """End-to-end pipeline: extract, transform, load, and report."""
    lines = extract_log_lines(LOG_FILE)
    parsed = transform_log_entries(lines)

    error_counts = aggregate_errors(parsed.errors)
    api_stats = aggregate_api_latency(parsed.api_calls)
    active_sessions = count_active_sessions(parsed.user_events)

    load_to_db(DB_PATH, error_counts, api_stats)
    generate_report(error_counts, api_stats, active_sessions)

    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    run_pipeline()