"""Pipeline for processing server logs and generating system reports.

Follows the Extract → Transform → Load pattern:

    Extract   parse_log_line  →  extract_logs
    Transform count_errors  |  compute_api_latency  |  compute_active_sessions
    Load      init_db  →  insert_summaries  →  generate_report_html  →  write_report
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    output_file: str


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults."""
    return Config(
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        log_file=os.environ.get("LOG_FILE", "server.log"),
        output_file=os.environ.get("OUTPUT_FILE", "report.html"),
    )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class UserEntry:
    """A parsed INFO-level log line describing a user action (login/logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEntry:
    """A parsed INFO-level log line describing an API call with duration."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarnEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


# ---------------------------------------------------------------------------
# Extract — parse raw log lines into typed records
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
)
_USER_PATTERN = re.compile(r"^User (\S+) (.*)$")
_API_PATTERN = re.compile(r"^API (\S+) took (\d+)ms$")

_LOG_TS_GROUP = 1
_LOG_LEVEL_GROUP = 2
_LOG_MSG_GROUP = 3
_USER_ID_GROUP = 1
_USER_ACTION_GROUP = 2
_API_ENDPOINT_GROUP = 1
_API_DURATION_GROUP = 2


def parse_log_line(line: str) -> Optional[
    Tuple[str, str, str]
]:
    """Parse a single log line into ``(timestamp, level, message)``.

    Returns ``None`` when the line does not match the expected format::

        YYYY-MM-DD HH:MM:SS LEVEL free-form message
    """
    match = _LOG_PATTERN.match(line.strip())
    if match is None:
        return None
    return (match.group(_LOG_TS_GROUP), match.group(_LOG_LEVEL_GROUP),
            match.group(_LOG_MSG_GROUP))


def extract_logs(log_path: str) -> Tuple[
    List[ErrorEntry],
    List[UserEntry],
    List[ApiEntry],
    List[WarnEntry],
]:
    """Read *log_path* and classify every line into typed record lists.

    Returns the tuple ``(errors, user_events, api_calls, warnings)``.
    Unparseable lines are silently skipped.
    """
    errors: List[ErrorEntry] = []
    user_events: List[UserEntry] = []
    api_calls: List[ApiEntry] = []
    warnings: List[WarnEntry] = []

    if not os.path.exists(log_path):
        return errors, user_events, api_calls, warnings

    with open(log_path, "r") as f:
        for line in f:
            parsed = parse_log_line(line)
            if parsed is None:
                continue
            ts, level, message = parsed

            if level == "ERROR":
                errors.append(ErrorEntry(timestamp=ts, message=message))

            elif level == "INFO":
                user_match = _USER_PATTERN.match(message)
                if user_match is not None:
                    uid = user_match.group(_USER_ID_GROUP)
                    action = user_match.group(_USER_ACTION_GROUP)
                    user_events.append(
                        UserEntry(timestamp=ts, user_id=uid, action=action)
                    )
                    continue

                api_match = _API_PATTERN.match(message)
                if api_match is not None:
                    api_calls.append(
                        ApiEntry(
                            timestamp=ts,
                            endpoint=api_match.group(_API_ENDPOINT_GROUP),
                            duration_ms=int(api_match.group(_API_DURATION_GROUP)),
                        )
                    )

            elif level == "WARN":
                warnings.append(WarnEntry(timestamp=ts, message=message))

    return errors, user_events, api_calls, warnings


# ---------------------------------------------------------------------------
# Transform — derive summaries from parsed records
# ---------------------------------------------------------------------------


def count_errors(errors: List[ErrorEntry]) -> Dict[str, int]:
    """Count occurrences of each unique error message.

    Returns a dict mapping ``message → count``, sorted by frequency
    (most common first).
    """
    counts: Dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return dict(
        sorted(counts.items(), key=lambda item: item[1], reverse=True)
    )


def compute_api_latency(api_calls: List[ApiEntry]) -> Dict[str, List[int]]:
    """Group API call durations by endpoint.

    Returns a dict mapping ``endpoint → list of durations in ms``.
    """
    groups: Dict[str, List[int]] = {}
    for call in api_calls:
        groups.setdefault(call.endpoint, []).append(call.duration_ms)
    return groups


def compute_active_sessions(
    user_events: List[UserEntry],
) -> Dict[str, str]:
    """Replay user login/logout events to determine currently active sessions.

    Returns a dict mapping ``user_id → login_timestamp`` for every user
    whose last event was a login (i.e. they have not logged out).
    """
    sessions: Dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            del sessions[event.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load — persist summaries to SQLite and write the HTML report
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """Create the ``errors`` and ``api_metrics`` tables if they don't exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def insert_summaries(
    conn: sqlite3.Connection,
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
) -> None:
    """Insert error counts and API latency averages into the database.

    Uses parameterised queries to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()

    for message, count in error_summary.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, durations in api_latency.items():
        avg = sum(durations) / len(durations)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()


def generate_report_html(
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_session_count: int,
) -> str:
    """Build a standalone HTML report as a string."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in error_summary.items():
        lines.append(
            f"<li><b>{_escape_html(message)}</b>: "
            f"{count} occurrences</li>"
        )
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>",
                   "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])
    for endpoint, durations in api_latency.items():
        avg = sum(durations) / len(durations)
        escaped = _escape_html(endpoint)
        lines.append(
            f"<tr><td>{escaped}</td><td>{avg:.1f}</td></tr>"
        )
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Minimal HTML-entity escaping for safe embedding in HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_report(html: str, output_path: str) -> None:
    """Write *html* to *output_path*."""
    with open(output_path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline(config: Config) -> None:
    """Run the full Extract → Transform → Load pipeline.

    Args:
        config: Runtime configuration (paths, etc.).
    """
    errors, user_events, api_calls, _warnings = extract_logs(config.log_file)
    error_summary = count_errors(errors)
    api_latency = compute_api_latency(api_calls)
    sessions = compute_active_sessions(user_events)

    conn = sqlite3.connect(config.db_path)
    try:
        init_db(conn)
        insert_summaries(conn, error_summary, api_latency)
    finally:
        conn.close()

    html = generate_report_html(error_summary, api_latency, len(sessions))
    write_report(html, config.output_file)

    print(f"Report written to {config.output_file}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

_SEED_LOG_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in\n",
    "2024-01-01 12:05:00 ERROR Database timeout\n",
    "2024-01-01 12:05:05 ERROR Database timeout\n",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
    "2024-01-01 12:10:00 INFO User 42 logged out\n",
]


def _seed_log_file(log_path: str) -> None:
    """Write a minimal sample log file if none exists."""
    with open(log_path, "w") as f:
        f.writelines(_SEED_LOG_LINES)


def main() -> None:
    """Entry point: create seed data if needed, then run the pipeline."""
    config = load_config()
    if not os.path.exists(config.log_file):
        _seed_log_file(config.log_file)
    run_pipeline(config)


if __name__ == "__main__":
    main()
