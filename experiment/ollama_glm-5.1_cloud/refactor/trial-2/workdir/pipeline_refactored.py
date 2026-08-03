"""Server-log ETL pipeline: extract → transform → load.

Reads server logs, computes error summaries, API latency averages,
and active-session counts, then writes results to SQLite and an
HTML report.

All configuration comes from environment variables; nothing is
hardcoded.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Configuration – every value is sourced from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("REPORT_PATH", "report.html")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "")  # no default credential


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class ErrorEntry(NamedTuple):
    """An error event extracted from the log."""
    timestamp: str
    message: str


class UserEvent(NamedTuple):
    """A user login / logout event."""
    timestamp: str
    user_id: str
    action: str


class ApiCall(NamedTuple):
    """An API call with its latency."""
    timestamp: str
    endpoint: str
    duration_ms: int


class WarningEntry(NamedTuple):
    """A warning event extracted from the log."""
    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all records extracted from a log file."""
    errors: list[ErrorEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarningEntry] = field(default_factory=list)


@dataclass
class TransformedData:
    """Aggregated results ready for loading."""
    error_summary: dict[str, int]          # message → count
    api_latency: dict[str, list[int]]      # endpoint → [durations]
    active_sessions: dict[str, str]         # user_id → login timestamp


# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# 2024-01-01 12:05:00 ERROR Database timeout
_RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+ERROR\s+(?P<msg>.+)$"
)

# 2024-01-01 12:00:00 INFO User 42 logged in
_RE_USER_EVENT = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

# 2024-01-01 12:08:00 INFO API /users/profile took 250ms
_RE_API_CALL = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+INFO\s+API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)

# 2024-01-01 12:09:00 WARN Memory usage at 87%
_RE_WARNING = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+WARN\s+(?P<msg>.+)$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def extract(log_path: str) -> ParsedLog:
    """Parse every line in *log_path* into structured records.

    Uses compiled regexes instead of fragile ``str.split`` so that
    minor format variations (extra whitespace, longer messages) don't
    silently break parsing.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ``ParsedLog`` with all recognised records.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        return parsed

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue

            m = _RE_ERROR.match(line)
            if m:
                parsed.errors.append(
                    ErrorEntry(timestamp=m.group("ts"), message=m.group("msg"))
                )
                continue

            m = _RE_API_CALL.match(line)
            if m:
                parsed.api_calls.append(
                    ApiCall(
                        timestamp=m.group("ts"),
                        endpoint=m.group("endpoint"),
                        duration_ms=int(m.group("ms")),
                    )
                )
                continue

            m = _RE_USER_EVENT.match(line)
            if m:
                parsed.user_events.append(
                    UserEvent(
                        timestamp=m.group("ts"),
                        user_id=m.group("uid"),
                        action=m.group("action").strip(),
                    )
                )
                continue

            m = _RE_WARNING.match(line)
            if m:
                parsed.warnings.append(
                    WarningEntry(timestamp=m.group("ts"), message=m.group("msg"))
                )

    return parsed


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform(parsed: ParsedLog) -> TransformedData:
    """Aggregate extracted records into report-ready summaries.

    Args:
        parsed: The raw records from ``extract``.

    Returns:
        Error counts, per-endpoint latencies, and active sessions.
    """
    # Error message → occurrence count
    error_summary: dict[str, int] = {}
    for entry in parsed.errors:
        error_summary[entry.message] = error_summary.get(entry.message, 0) + 1

    # Endpoint → list of durations (for averaging later)
    api_latency: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.duration_ms)

    # Active sessions: logged-in users who haven't logged out
    sessions: dict[str, str] = {}
    for evt in parsed.user_events:
        if evt.action == "logged in":
            sessions[evt.user_id] = evt.timestamp
        elif evt.action == "logged out" and evt.user_id in sessions:
            del sessions[evt.user_id]

    return TransformedData(
        error_summary=error_summary,
        api_latency=api_latency,
        active_sessions=sessions,
    )


# ---------------------------------------------------------------------------
# LOAD – database
# ---------------------------------------------------------------------------

def load_to_db(data: TransformedData, db_path: str) -> None:
    """Write aggregated metrics to a SQLite database.

    Uses parameterised queries exclusively — no string interpolation
    in SQL statements.

    Args:
        data: Aggregated data from ``transform``.
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        for msg, count in data.error_summary.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in data.api_latency.items():
            avg = sum(times) / len(times)
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LOAD – HTML report
# ---------------------------------------------------------------------------

def load_to_html(data: TransformedData, report_path: str) -> None:
    """Render an HTML report summarising errors, latency, and sessions.

    The output structure (headings, table, list) matches the original
    ``report.html`` exactly.

    Args:
        data: Aggregated data from ``transform``.
        report_path: Path to write the HTML file to.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in data.error_summary.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in data.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(data.active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline: extract → transform → load.

    Reads the server log, transforms it into aggregated metrics,
    persists results to SQLite and writes an HTML report.
    """
    # Seed a sample log when the file is missing (mirrors original behaviour).
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    parsed = extract(LOG_FILE)

    # Transform
    data = transform(parsed)

    # Load
    load_to_db(data, DB_PATH)
    load_to_html(data, REPORT_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()