"""Server-log pipeline: extract, transform, load.

Reads server logs, aggregates error/API/session data, persists results
to SQLite, and writes an HTML report.

All configuration is sourced from environment variables:

    DB_PATH     – SQLite database file          (default: metrics.db)
    LOG_FILE    – Server log file path          (default: server.log)
    DB_HOST     – Database host                 (default: localhost)
    DB_PORT     – Database port                 (default: 5432)
    DB_USER     – Database user                 (default: admin)
    DB_PASS     – Database password             (default: password123)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# Generic: "2024-01-01 12:00:00 LEVEL ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<rest>.*)$"
)

# ERROR line – everything after the level is the message
# (no special sub-pattern needed; captured by ``rest``)

# INFO User line: "INFO User 42 logged in" / "INFO User 42 logged out"
_USER_RE = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

# INFO API line: "INFO API /users/profile took 250ms"
_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str


@dataclass
class ErrorEntry(LogEntry):
    level: str = "ERROR"
    message: str = ""


@dataclass
class UserEntry(LogEntry):
    level: str = "INFO"
    uid: str = ""
    action: str = ""


@dataclass
class ApiCallEntry(LogEntry):
    level: str = "INFO"
    endpoint: str = ""
    ms: int = 0


@dataclass
class WarnEntry(LogEntry):
    level: str = "WARN"
    message: str = ""


@dataclass
class ParsedLog:
    """Container for all data extracted from the log file."""

    errors: List[ErrorEntry] = field(default_factory=list)
    user_events: List[UserEntry] = field(default_factory=list)
    api_calls: List[ApiCallEntry] = field(default_factory=list)
    warnings: List[WarnEntry] = field(default_factory=list)


@dataclass
class AggregatedReport:
    """Aggregated results ready for loading."""

    error_counts: Dict[str, int] = field(default_factory=dict)
    endpoint_avg_ms: Dict[str, float] = field(default_factory=dict)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Extract – read and parse the log file
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Parse *log_path* into structured records.

    Uses regex patterns to robustly extract timestamp, level, and
    level-specific fields (error messages, user actions, API endpoints
    and latencies, warnings).

    Args:
        log_path: Path to the server log file.

    Returns:
        A :class:`ParsedLog` containing categorized entries.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return parsed

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                parsed.errors.append(
                    ErrorEntry(timestamp=timestamp, level=level, message=rest)
                )

            elif level == "INFO" and rest.startswith("User "):
                user_match = _USER_RE.match(rest)
                if user_match:
                    parsed.user_events.append(
                        UserEntry(
                            timestamp=timestamp,
                            level=level,
                            uid=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )

            elif level == "INFO" and rest.startswith("API "):
                api_match = _API_RE.match(rest)
                if api_match:
                    ms_val = int(api_match.group("ms")) if api_match.group("ms") else 0
                    parsed.api_calls.append(
                        ApiCallEntry(
                            timestamp=timestamp,
                            level=level,
                            endpoint=api_match.group("endpoint"),
                            ms=ms_val,
                        )
                    )

            elif level == "WARN":
                parsed.warnings.append(
                    WarnEntry(timestamp=timestamp, level=level, message=rest)
                )

    return parsed


# ---------------------------------------------------------------------------
# Transform – aggregate into report data
# ---------------------------------------------------------------------------


def transform(parsed: ParsedLog) -> AggregatedReport:
    """Aggregate parsed log entries into report data.

    Computes:
      - Error message frequency.
      - Per-endpoint average API latency.
      - Count of currently active sessions (logins minus logouts).

    Args:
        parsed: The extracted log data.

    Returns:
        An :class:`AggregatedReport` with computed summaries.
    """
    # Error counts
    error_counts: Dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # API latency averages
    endpoint_times: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.ms)

    endpoint_avg_ms: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_times.items()
    }

    # Active sessions
    active_sessions: Dict[str, str] = {}
    for event in parsed.user_events:
        if "logged in" in event.action:
            active_sessions[event.uid] = event.timestamp
        elif "logged out" in event.action and event.uid in active_sessions:
            del active_sessions[event.uid]

    return AggregatedReport(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_sessions=len(active_sessions),
    )


# ---------------------------------------------------------------------------
# Load – persist to DB and generate HTML report
# ---------------------------------------------------------------------------


def load(
    report: AggregatedReport,
    db_path: str,
    report_path: str = "report.html",
) -> None:
    """Persist aggregated data to SQLite and write an HTML report.

    Uses parameterized queries throughout to prevent SQL injection.

    Args:
        report: Aggregated report data to persist.
        db_path: Path to the SQLite database file.
        report_path: Path for the output HTML report file.
    """
    now = datetime.datetime.now().isoformat()

    # --- Database ---
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in report.error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg_ms in report.endpoint_avg_ms.items():
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()
    conn.close()

    # --- HTML report ---
    html = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        "<h1>Error Summary</h1>\n<ul>\n"
    )
    for err_msg, count in report.error_counts.items():
        html += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg_ms in report.endpoint_avg_ms.items():
        html += f"<tr><td>{ep}</td><td>{round(avg_ms, 1)}</td></tr>\n"
    html += "</table>\n"

    html += "<h2>Active Sessions</h2>\n"
    html += f"<p>{report.active_sessions} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    with open(report_path, "w") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    parsed = extract(LOG_FILE)
    report = transform(parsed)
    load(report, DB_PATH)


if __name__ == "__main__":
    # Create a sample log file for demonstration when none exists.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()