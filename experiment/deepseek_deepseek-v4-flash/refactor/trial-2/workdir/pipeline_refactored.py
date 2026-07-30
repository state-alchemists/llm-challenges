#!/usr/bin/env python3
"""Extract, transform, and load server logs into SQLite, then generate an HTML report.

Usage:
    LOG_FILE=server.log DB_PATH=metrics.db python pipeline_refactored.py

All configuration is read from environment variables (see load_config docstring
for the full list). If the log file does not exist, a sample log is created
automatically before processing.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>.+)$")

_API_RE = re.compile(r"^API (?P<endpoint>/\S+) took (?P<duration>\d+)ms$")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration read from environment variables."""

    log_file: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEntry:
    """A parsed log line recording user login/logout activity."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEntry:
    """A parsed log line recording an API call and its duration in ms."""

    timestamp: str
    endpoint: str
    duration_ms: int


type LogEntry = ErrorEntry | UserEntry | ApiEntry


# ---------------------------------------------------------------------------
# Extract phase
# ---------------------------------------------------------------------------


def load_config() -> Config:
    """Read all configuration from environment variables.

    Env vars read:
        LOG_FILE  — path to the server log (default: server.log)
        DB_PATH   — path to the SQLite database file (default: metrics.db)
        DB_HOST   — database host (informational; unused with SQLite)
        DB_PORT   — database port (informational; unused with SQLite)
        DB_USER   — database user (informational; unused with SQLite)
        DB_PASS   — database password (informational; unused with SQLite)
    """
    return Config(
        log_file=Path(os.getenv("LOG_FILE", "server.log")),
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


def read_log_lines(path: Path) -> List[str]:
    """Return all non-empty lines from *path*.

    Returns an empty list if the file does not exist.
    """
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def parse_log_entry(line: str) -> LogEntry | None:
    """Parse a single log line into a structured LogEntry, or ``None`` if
    the line does not match the expected format."""
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None

    ts = m.group("timestamp")
    level = m.group("level")
    msg = m.group("message")

    if level == "ERROR":
        return ErrorEntry(timestamp=ts, message=msg)

    if level == "WARN":
        # WARN entries carry no structured sub-payload; store the raw message.
        pass

    if level == "INFO":
        user_m = _USER_RE.match(msg)
        if user_m:
            return UserEntry(
                timestamp=ts,
                user_id=user_m.group("user_id"),
                action=user_m.group("action"),
            )
        api_m = _API_RE.match(msg)
        if api_m:
            return ApiEntry(
                timestamp=ts,
                endpoint=api_m.group("endpoint"),
                duration_ms=int(api_m.group("duration")),
            )

    return None


def extract_logs(path: Path) -> List[LogEntry]:
    """Read and parse all log lines from *path*.

    Lines that cannot be parsed are silently skipped.
    """
    return [e for line in read_log_lines(path) if (e := parse_log_entry(line)) is not None]


# ---------------------------------------------------------------------------
# Transform phase
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AggregatedData:
    """Container for all computed statistics from the log entries."""

    error_summary: Dict[str, int]
    api_latency: Dict[str, float]
    active_session_count: int


def process_logs(entries: List[LogEntry]) -> AggregatedData:
    """Aggregate error counts, API latency, and active sessions from parsed
    log entries in a single pass.

    Session tracking: a user is considered active after a "logged in" action
    and removed after "logged out". The final count is the number of sessions
    that are still open at the end of the log.
    """
    error_summary: Dict[str, int] = defaultdict(int)
    raw_api_calls: Dict[str, List[int]] = defaultdict(list)
    sessions: Dict[str, str] = {}

    for entry in entries:
        match entry:
            case ErrorEntry(message=msg):
                error_summary[msg] += 1

            case ApiEntry(endpoint=ep, duration_ms=ms):
                raw_api_calls[ep].append(ms)

            case UserEntry(user_id=uid, action=action, timestamp=ts):
                if "logged in" in action:
                    sessions[uid] = ts
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]

            case _:
                pass  # WARN entries are not aggregated in the current spec.

    api_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in raw_api_calls.items()
    }

    return AggregatedData(
        error_summary=dict(error_summary),
        api_latency=api_latency,
        active_session_count=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load phase
# ---------------------------------------------------------------------------


def init_database(path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database at *path* and ensure the required
    tables exist."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def store_error_summary(conn: sqlite3.Connection, summary: Dict[str, int]) -> None:
    """Insert error summary rows into the database using parameterized queries.

    Each row receives the current timestamp to record when the report was run.
    """
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, count) for msg, count in summary.items()],
    )


def store_api_latency(conn: sqlite3.Connection, latency: Dict[str, float]) -> None:
    """Insert API latency rows into the database using parameterized queries.

    Each row receives the current timestamp to record when the report was run.
    """
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in latency.items()],
    )


def generate_report(data: AggregatedData) -> str:
    """Build the HTML report string from aggregated data.

    Contains three sections: error summary (list), API latency (table),
    and active session count.
    """
    return (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        + _build_error_section(data.error_summary)
        + _build_api_section(data.api_latency)
        + _build_session_section(data.active_session_count)
        + "</body>\n</html>"
    )


def _build_error_section(errors: Dict[str, int]) -> str:
    """HTML for the error summary section."""
    lines = ["<h1>Error Summary</h1>\n<ul>"]
    lines.extend(
        f"<li><b>{msg}</b>: {count} occurrences</li>" for msg, count in errors.items()
    )
    lines.append("</ul>\n")
    return "\n".join(lines)


def _build_api_section(latency: Dict[str, float]) -> str:
    """HTML for the API latency table."""
    lines = [
        "<h2>API Latency</h2>\n<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for ep, avg in latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{avg}</td></tr>")
    lines.append("</table>\n")
    return "\n".join(lines)


def _build_session_section(count: int) -> str:
    """HTML for the active sessions paragraph."""
    return f"<h2>Active Sessions</h2>\n<p>{count} user(s) currently active</p>\n"


def write_report(path: Path, html: str) -> None:
    """Write the HTML report to *path*."""
    path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_LOG_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


def _create_sample_log(path: Path) -> None:
    """Write a sample server log file if it does not already exist."""
    path.write_text("\n".join(_SAMPLE_LOG_LINES) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full pipeline: extract → transform → load → report."""
    cfg = load_config()

    if not cfg.log_file.exists():
        _create_sample_log(cfg.log_file)

    print(f"Connecting to {cfg.db_host}:{cfg.db_port} as {cfg.db_user}...")

    entries = extract_logs(cfg.log_file)
    data = process_logs(entries)

    conn = init_database(cfg.db_path)
    try:
        store_error_summary(conn, data.error_summary)
        store_api_latency(conn, data.api_latency)
        conn.commit()
    finally:
        conn.close()

    html = generate_report(data)
    write_report(Path("report.html"), html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
