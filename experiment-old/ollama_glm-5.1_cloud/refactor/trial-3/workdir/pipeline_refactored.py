"""Pipeline for processing server logs, storing metrics, and generating reports.

Extracts log entries via regex, transforms them into error summaries
and API latency statistics, loads results into SQLite, and generates
an HTML report.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration – all values sourced from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A generic log line (errors and warnings)."""

    timestamp: str
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """An API call with latency measurement."""

    timestamp: str
    endpoint: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Compiled regex patterns for robust log parsing
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.+)$"
)
_USER_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.+)$"
)
_API_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"
)

# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(
    log_path: Path,
) -> tuple[list[LogEntry], list[UserEvent], list[ApiCall]]:
    """Parse the log file and return categorized entries.

    Uses compiled regex patterns to robustly match timestamp, level,
    and payload for each log line type (error, user event, API call,
    warning).
    """
    entries: list[LogEntry] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []

    if not log_path.exists():
        return entries, user_events, api_calls

    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            # Try API call pattern first (most specific)
            api_match = _API_PATTERN.match(line)
            if api_match:
                ts, endpoint, dur = api_match.groups()
                api_calls.append(
                    ApiCall(timestamp=ts, endpoint=endpoint, duration_ms=int(dur))
                )
                continue

            # Try user event pattern
            user_match = _USER_PATTERN.match(line)
            if user_match:
                ts, uid, action = user_match.groups()
                user_events.append(
                    UserEvent(timestamp=ts, user_id=uid, action=action)
                )
                continue

            # Fall back to generic log pattern (ERROR / WARN / misc INFO)
            generic_match = _LOG_PATTERN.match(line)
            if generic_match:
                ts, level, message = generic_match.groups()
                entries.append(LogEntry(timestamp=ts, level=level, message=message))

    return entries, user_events, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_error_summary(entries: list[LogEntry]) -> dict[str, int]:
    """Aggregate ERROR-level entries into a message-to-count mapping."""
    summary: dict[str, int] = {}
    for entry in entries:
        if entry.level == "ERROR":
            summary[entry.message] = summary.get(entry.message, 0) + 1
    return summary


def transform_api_stats(api_calls: list[ApiCall]) -> dict[str, list[int]]:
    """Group API call latencies by endpoint."""
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def transform_active_sessions(user_events: list[UserEvent]) -> int:
    """Count currently active sessions (logins minus logouts)."""
    sessions: dict[str, str] = {}
    for event in user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)
    return len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """Persist error and latency data into SQLite using parameterized queries."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.now().isoformat()
    for message, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in api_stats.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """Render an HTML report with error summary, API latency, and active sessions."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for message, count in error_summary.items():
        lines.append(f"<li><b>{message}</b>: {count} occurrences</li>")
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

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the Extract → Transform → Load pipeline."""
    log_path = Path(LOG_FILE)

    # Create a sample log for standalone runs
    if not log_path.exists():
        log_path.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )

    # Extract
    entries, user_events, api_calls = extract_log_entries(log_path)

    # Transform
    error_summary = transform_error_summary(entries)
    api_stats = transform_api_stats(api_calls)
    active_sessions = transform_active_sessions(user_events)

    # Load
    load_to_database(DB_PATH, error_summary, api_stats)

    # Report
    report_html = generate_report(error_summary, api_stats, active_sessions)
    Path("report.html").write_text(report_html, encoding="utf-8")

    print(f"Job finished at {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()