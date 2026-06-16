"""Refactored server-log processing pipeline.

Extracts log entries from a server log file, transforms them into aggregated
metrics (error counts, API latencies, active sessions), loads the results into
SQLite, and generates an HTML report.

All configuration is read from environment variables with sensible defaults.
"""

from __future__ import annotations

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
class ErrorEntry:
    """An aggregated error with its occurrence count."""

    message: str
    count: int


@dataclass
class ApiLatency:
    """Average response latency for a single API endpoint."""

    endpoint: str
    avg_ms: float


@dataclass
class LogParsingResult:
    """Aggregated output from log transformation."""

    errors: list[ErrorEntry] = field(default_factory=list)
    api_latencies: list[ApiLatency] = field(default_factory=list)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Compiled regex patterns for log-line parsing
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+)\s+(?P<rest>.*)$"
)

_USER_PATTERN = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")

_API_PATTERN = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: str) -> list[dict[str, str]]:
    """Read a server log file and return a list of parsed line dictionaries.

    Each dictionary contains keys ``timestamp``, ``level``, and ``rest``.
    Lines that don't match the expected log format are silently skipped.
    """
    path = Path(log_path)
    if not path.exists():
        return []

    entries: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_PATTERN.match(line.strip())
            if match:
                entries.append(
                    {
                        "timestamp": match.group("timestamp"),
                        "level": match.group("level"),
                        "rest": match.group("rest"),
                    }
                )
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_entries(entries: list[dict[str, str]]) -> LogParsingResult:
    """Aggregate parsed log entries into error counts, API latencies, and active sessions.

    Error messages are counted by unique text.  API latencies are averaged per
    endpoint.  Sessions track users who logged in but haven't logged out.
    """
    error_counts: dict[str, int] = {}
    api_times: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        level = entry["level"]
        rest = entry["rest"]

        if level == "ERROR":
            msg = rest.strip()
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif level == "INFO":
            user_match = _USER_PATTERN.match(rest)
            if user_match:
                uid = user_match.group("user_id")
                action = user_match.group("action").strip()
                if "logged in" in action:
                    sessions[uid] = entry["timestamp"]
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]
                continue

            api_match = _API_PATTERN.match(rest)
            if api_match:
                endpoint = api_match.group("endpoint")
                ms_str = api_match.group("duration_ms") or "0"
                api_times.setdefault(endpoint, []).append(int(ms_str))

        elif level == "WARN":
            # Warnings are logged but not aggregated in the report
            pass

    errors = [
        ErrorEntry(message=msg, count=count)
        for msg, count in error_counts.items()
    ]
    api_latencies = [
        ApiLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in api_times.items()
    ]
    return LogParsingResult(
        errors=errors,
        api_latencies=api_latencies,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(db_path: str, result: LogParsingResult) -> None:
    """Write aggregated error counts and API latencies into SQLite.

    Uses parameterized queries to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for err in result.errors:
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, err.message, err.count),
            )

        for lat in result.api_latencies:
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, lat.endpoint, lat.avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    result: LogParsingResult,
    output_path: str = "report.html",
) -> None:
    """Render an HTML report with error summary, API latency table, and active sessions."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err in result.errors:
        lines.append(f"<li><b>{err.message}</b>: {err.count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for lat in result.api_latencies:
        lines.append(
            f"<tr><td>{lat.endpoint}</td><td>{round(lat.avg_ms, 1)}</td></tr>"
        )

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{result.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the Extract → Transform → Load pipeline."""
    # Ensure a sample log file exists for demo purposes
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    entries = extract_log_entries(LOG_FILE)
    result = transform_entries(entries)
    load_to_database(DB_PATH, result)
    generate_report(result)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()