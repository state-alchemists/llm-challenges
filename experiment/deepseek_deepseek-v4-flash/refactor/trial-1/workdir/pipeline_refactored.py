"""Pipeline: extract logs → transform → load → HTML report.

Usage::

    LOG_FILE_PATH=server.log DB_PATH=metrics.db python pipeline_refactored.py

All configuration is read from environment variables (see :class:`Settings`).
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


@dataclass
class Settings:
    """Runtime configuration loaded from environment variables.

    Every field falls back to a sensible default so the script runs without
    any env vars set (useful for local testing).
    """

    log_file_path: str = field(
        default_factory=lambda: os.getenv("LOG_FILE_PATH", "server.log")
    )
    db_path: str = field(
        default_factory=lambda: os.getenv("DB_PATH", "metrics.db")
    )
    db_host: str = field(
        default_factory=lambda: os.getenv("DB_HOST", "localhost")
    )
    db_port: int = field(
        default_factory=lambda: int(os.getenv("DB_PORT", "5432"))
    )
    db_user: str = field(
        default_factory=lambda: os.getenv("DB_USER", "admin")
    )
    db_pass: str = field(
        default_factory=lambda: os.getenv("DB_PASS", "password123")
    )


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """An ERROR-level log line."""
    timestamp: str
    message: str


@dataclass
class WarnEntry:
    """A WARN-level log line."""
    timestamp: str
    message: str


@dataclass
class UserEntry:
    """An INFO-level line describing a user login or logout."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEntry:
    """An INFO-level line recording an API call's duration."""
    timestamp: str
    endpoint: str
    duration_ms: int


LogEntry = ErrorEntry | WarnEntry | UserEntry | ApiEntry


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|WARN|INFO|DEBUG)\s+"
    r"(?P<message>.+)$",
)
_USER_ACTION_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract phase
# ---------------------------------------------------------------------------


def extract_logs(file_path: str) -> list[LogEntry]:
    """Parse a log file and return typed log entries.

    Each line is expected to follow the format::

        YYYY-MM-DD HH:MM:SS LEVEL message

    Sub-parsing is applied based on the *message* content:

    * ``ERROR message`` → :class:`ErrorEntry`
    * ``WARN message``  → :class:`WarnEntry`
    * ``INFO User <id> <action>`` → :class:`UserEntry`
    * ``INFO API <endpoint> took <N>ms`` → :class:`ApiEntry`

    Args:
        file_path: Path to the server log file.

    Returns:
        A list of parsed entries.  Unrecognised lines are silently skipped.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
    """
    entries: list[LogEntry] = []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m = _LINE_RE.match(line)
            if m is None:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            message = m.group("message")

            if level == "ERROR":
                entries.append(ErrorEntry(timestamp=timestamp, message=message))
            elif level == "WARN":
                entries.append(WarnEntry(timestamp=timestamp, message=message))
            elif level == "INFO":
                user_m = _USER_ACTION_RE.match(message)
                if user_m is not None:
                    entries.append(
                        UserEntry(
                            timestamp=timestamp,
                            user_id=user_m.group("user_id"),
                            action=user_m.group("action"),
                        )
                    )
                else:
                    api_m = _API_RE.match(message)
                    if api_m is not None:
                        entries.append(
                            ApiEntry(
                                timestamp=timestamp,
                                endpoint=api_m.group("endpoint"),
                                duration_ms=int(api_m.group("ms")),
                            )
                        )
            # DEBUG lines are silently skipped.

    return entries


# ---------------------------------------------------------------------------
# Transform phase
# ---------------------------------------------------------------------------


def count_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each unique error message.

    Args:
        entries: Parsed log entries.

    Returns:
        Error message → count, sorted by frequency (most frequent first).
    """
    counter: dict[str, int] = {}
    for e in entries:
        if isinstance(e, ErrorEntry):
            counter[e.message] = counter.get(e.message, 0) + 1
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def compute_api_latency(entries: list[LogEntry]) -> dict[str, float]:
    """Compute average response time per API endpoint.

    Args:
        entries: Parsed log entries.

    Returns:
        Endpoint → average duration in milliseconds.
    """
    durations: dict[str, list[int]] = {}
    for e in entries:
        if isinstance(e, ApiEntry):
            durations.setdefault(e.endpoint, []).append(e.duration_ms)
    return {ep: sum(times) / len(times) for ep, times in durations.items()}


def compute_active_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """Replay user login/logout events to determine currently active sessions.

    Args:
        entries: Parsed log entries.

    Returns:
        User ID → login timestamp for every user who logged in but has not
        yet logged out.
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if isinstance(e, UserEntry):
            if "logged in" in e.action:
                sessions[e.user_id] = e.timestamp
            elif "logged out" in e.action and e.user_id in sessions:
                del sessions[e.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load phase
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS errors (
    dt      TEXT NOT NULL,
    message TEXT NOT NULL,
    count   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_metrics (
    dt      TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    avg_ms  REAL NOT NULL
);
"""

_INSERT_ERROR_SQL = "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)"
_INSERT_API_SQL = "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)"


def load_results(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    db_path: str,
) -> None:
    """Persist aggregated results into a SQLite database.

    Tables are created on first run.  All rows are inserted in a single
    transaction so the DB is never left in a half-written state.

    Args:
        error_counts:  Error message → occurrence count.
        api_latency:   Endpoint → average latency (ms).
        db_path:       Path to the SQLite database file.
    """
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)

        conn.executemany(
            _INSERT_ERROR_SQL,
            [(now, msg, cnt) for msg, cnt in error_counts.items()],
        )
        conn.executemany(
            _INSERT_API_SQL,
            [(now, ep, avg) for ep, avg in api_latency.items()],
        )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Minimal HTML-entity escaping for safe text interpolation."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_report(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Write an HTML system report to disk.

    Sections:

    1. **Error Summary** — each unique error and its occurrence count.
    2. **API Latency** — table of endpoints and average response times.
    3. **Active Sessions** — number of currently logged-in users.

    Args:
        error_counts:    Error message → occurrence count.
        api_latency:     Endpoint → average latency (ms).
        active_sessions: User ID → session start timestamp.
        output_path:     Destination path for the HTML file.
    """
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head><meta charset='utf-8'><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        parts.append(
            f"<li><b>{_escape_html(msg)}</b>: {count} occurrences</li>"
        )
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in api_latency.items():
        parts.append(
            f"<tr><td>{_escape_html(ep)}</td><td>{avg:.1f}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{len(active_sessions)} user(s) currently active</p>")

    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(parts))

    print(f"Report written to {output_path}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _write_sample_log(path: str) -> None:
    """Create a minimal sample log file for first-run demo purposes."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Sample log written to {path}")


def main() -> None:
    """Run the full pipeline: extract → transform → load → report."""
    settings = Settings()

    print(
        f"Connecting to {settings.db_host}:{settings.db_port} "
        f"as {settings.db_user}..."
    )

    if not os.path.exists(settings.log_file_path):
        _write_sample_log(settings.log_file_path)

    # ── Extract ──────────────────────────────────────────────────────
    entries = extract_logs(settings.log_file_path)
    print(f"Extracted {len(entries)} log entries.")

    # ── Transform ────────────────────────────────────────────────────
    error_counts = count_errors(entries)
    api_latency = compute_api_latency(entries)
    active_sessions = compute_active_sessions(entries)

    # ── Load ─────────────────────────────────────────────────────────
    load_results(error_counts, api_latency, settings.db_path)
    print("Results written to database.")

    # ── Report ───────────────────────────────────────────────────────
    generate_report(error_counts, api_latency, active_sessions)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
