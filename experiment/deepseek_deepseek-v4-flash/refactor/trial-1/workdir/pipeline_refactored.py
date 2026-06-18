"""
Process server logs, extract metrics, and generate an HTML system report.

Usage
-----
    python pipeline_refactored.py

Configuration
-------------
All settings are read from environment variables with sensible defaults:

    LOG_FILE       path to the server log (default: server.log)
    DB_PATH        path to the SQLite database (default: metrics.db)
    DB_HOST        database hostname (unused by SQLite, for future use)
    DB_PORT        database port (unused by SQLite, for future use)
    DB_USER        database user (unused by SQLite, for future use)
    DB_PASS        database password (unused by SQLite, for future use)

Output
------
    report.html    HTML report with error summary, API latency table,
                   and active-session count.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Immutable runtime configuration loaded from environment variables."""

    log_file: str = "server.log"
    db_path: str = "metrics.db"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "admin"
    db_pass: str = "password123"

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables, falling back to defaults."""
        return cls(
            log_file=os.environ.get("LOG_FILE", "server.log"),
            db_path=os.environ.get("DB_PATH", "metrics.db"),
            db_host=os.environ.get("DB_HOST", "localhost"),
            db_port=int(os.environ.get("DB_PORT", "5432")),
            db_user=os.environ.get("DB_USER", "admin"),
            db_pass=os.environ.get("DB_PASS", "password123"),
        )


# ---------------------------------------------------------------------------
# Data model for parsed log entries
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A single parsed line from the server log."""

    timestamp: str
    level: str  # ERROR, WARN, or INFO


@dataclass
class ErrorEntry(LogEntry):
    """An ERROR-level log entry."""

    message: str


@dataclass
class WarnEntry(LogEntry):
    """A WARN-level log entry."""

    message: str


@dataclass
class UserActionEntry(LogEntry):
    """An INFO-level entry describing a user login or logout."""

    user_id: str
    action: str  # e.g. "logged in", "logged out"


@dataclass
class ApiCallEntry(LogEntry):
    """An INFO-level entry recording an API call duration."""

    endpoint: str
    duration_ms: int


LogLine = ErrorEntry | WarnEntry | UserActionEntry | ApiCallEntry


# ---------------------------------------------------------------------------
# Phase 1: Extract
# ---------------------------------------------------------------------------

# Regex for the common log-line prefix: timestamp + level.
_LOG_PREFIX_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<message>.+)$"
)

# Regex to extract user id and action from lines like
# "User 42 logged in" / "User 42 logged out".
_USER_ACTION_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# Regex to extract API endpoint and duration from lines like
# "API /users/profile took 250ms".
_API_CALL_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)" r"(?:\s+took\s+(?P<duration>\d+)ms)?"
)


def parse_log_line(line: str) -> Optional[LogLine]:
    """Parse a single server log line into a typed LogLine, or *None* if
    the line does not match the expected format.

    Recognised formats (examples)::

        2024-01-01 12:05:00 ERROR Database timeout
        2024-01-01 12:09:00 WARN Memory usage at 87%
        2024-01-01 12:00:00 INFO User 42 logged in
        2024-01-01 12:08:00 INFO API /users/profile took 250ms
    """
    m = _LOG_PREFIX_RE.match(line.strip())
    if not m:
        return None

    timestamp = m.group("timestamp")
    level = m.group("level")
    message = m.group("message")

    if level == "ERROR":
        return ErrorEntry(timestamp=timestamp, level=level, message=message)

    if level == "WARN":
        return WarnEntry(timestamp=timestamp, level=level, message=message)

    # Level is INFO — dispatch on message content.
    user_m = _USER_ACTION_RE.match(message)
    if user_m:
        return UserActionEntry(
            timestamp=timestamp,
            level=level,
            user_id=user_m.group("user_id"),
            action=user_m.group("action"),
        )

    api_m = _API_CALL_RE.match(message)
    if api_m:
        duration_str = api_m.group("duration")
        return ApiCallEntry(
            timestamp=timestamp,
            level=level,
            endpoint=api_m.group("endpoint"),
            duration_ms=int(duration_str) if duration_str else 0,
        )

    # INFO line that doesn't match any known subtype — skip silently.
    return None


def extract_logs(filepath: str) -> List[LogLine]:
    """Read and parse every line in the log file. Malformed lines are
    silently skipped.
    """
    entries: List[LogLine] = []
    if not os.path.exists(filepath):
        return entries

    with open(filepath, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Phase 2: Transform
# ---------------------------------------------------------------------------


def build_error_summary(errors: List[ErrorEntry]) -> Dict[str, int]:
    """Count occurrences of each unique error message.

    Returns
    -------
    dict
        Mapping of ``error message -> count``, sorted descending by count.
    """
    summary: Dict[str, int] = {}
    for e in errors:
        summary[e.message] = summary.get(e.message, 0) + 1
    # Sort descending by count for stable output.
    return dict(sorted(summary.items(), key=lambda kv: (-kv[1], kv[0])))


def build_api_latency_stats(
    api_calls: List[ApiCallEntry],
) -> Dict[str, List[int]]:
    """Group API-call durations by endpoint.

    Returns
    -------
    dict
        Mapping of ``endpoint -> list of duration_ms values``.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def track_active_sessions(actions: List[UserActionEntry]) -> Dict[str, str]:
    """Replay login/logout events to determine currently active sessions.

    Returns
    -------
    dict
        Mapping of ``user_id -> login_timestamp`` for users who are
        logged in but have not yet logged out.
    """
    sessions: Dict[str, str] = {}
    for a in actions:
        if a.action == "logged in":
            sessions[a.user_id] = a.timestamp
        elif a.action == "logged out" and a.user_id in sessions:
            del sessions[a.user_id]
    return sessions


def _classify_entries(
    entries: List[LogLine],
) -> Tuple[
    List[ErrorEntry], List[WarnEntry], List[UserActionEntry], List[ApiCallEntry]
]:
    """Split a mixed list of LogLine entries into per-type lists."""
    errors: List[ErrorEntry] = []
    warns: List[WarnEntry] = []
    user_actions: List[UserActionEntry] = []
    api_calls: List[ApiCallEntry] = []

    for e in entries:
        if isinstance(e, ErrorEntry):
            errors.append(e)
        elif isinstance(e, WarnEntry):
            warns.append(e)
        elif isinstance(e, UserActionEntry):
            user_actions.append(e)
        elif isinstance(e, ApiCallEntry):
            api_calls.append(e)

    return errors, warns, user_actions, api_calls


# ---------------------------------------------------------------------------
# Phase 3: Load
# ---------------------------------------------------------------------------


def init_database(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure required tables exist.

    Returns an open connection; the caller is responsible for closing it.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def store_error_summary(
    conn: sqlite3.Connection, summary: Dict[str, int]
) -> None:
    """Insert error-count rows with a parameterised query."""
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in summary.items()],
    )


def store_api_metrics(
    conn: sqlite3.Connection, stats: Dict[str, List[int]]
) -> None:
    """Insert per-endpoint average-latency rows with a parameterised query."""
    now = datetime.datetime.now().isoformat()
    rows = []
    for endpoint, times in stats.items():
        avg = sum(times) / len(times)
        rows.append((now, endpoint, avg))
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        rows,
    )


def generate_report_html(
    error_summary: Dict[str, int],
    api_stats: Dict[str, List[int]],
    active_session_count: int,
) -> str:
    """Produce an HTML report string with error summary, API latency table,
    and active-session count.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_summary.items():
        lines.append(
            f"<li><b>{_html_escape(msg)}</b>: "
            f"{count} occurrences</li>"
        )
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in api_stats.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(
            f"<tr><td>{_html_escape(ep)}</td>"
            f"<td>{avg}</td></tr>"
        )
    lines.extend(["</table>", "<h2>Active Sessions</h2>"])
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.extend(["</body>", "</html>"])
    return "\n".join(lines)


def _html_escape(text: str) -> str:
    """Minimal HTML-entity escaping for safe string interpolation in HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_report(html: str, filepath: str) -> None:
    """Write the HTML report to disk."""
    with open(filepath, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def main() -> None:
    """Full pipeline: extract logs, compute metrics, store to DB, write
    HTML report.
    """
    config = Config.from_env()

    # --- Extract ---
    entries = extract_logs(config.log_file)

    # --- Transform ---
    errors, _warns, user_actions, api_calls = _classify_entries(entries)
    error_summary = build_error_summary(errors)
    api_stats = build_api_latency_stats(api_calls)
    active_sessions = track_active_sessions(user_actions)

    # --- Load (database) ---
    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )
    conn = init_database(config.db_path)
    try:
        store_error_summary(conn, error_summary)
        store_api_metrics(conn, api_stats)
        conn.commit()
    finally:
        conn.close()

    # --- Load (report) ---
    html = generate_report_html(
        error_summary=error_summary,
        api_stats=api_stats,
        active_session_count=len(active_sessions),
    )
    write_report(html, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _write_sample_log(filepath: str) -> None:
    """Write a minimal sample log if the file doesn't exist yet."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(filepath, "w") as f:
        for line in lines:
            f.write(line + "\n")


if __name__ == "__main__":
    config = Config.from_env()
    if not os.path.exists(config.log_file):
        _write_sample_log(config.log_file)
    main()
