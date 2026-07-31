"""Refactored pipeline: Extract → Transform → Load for server log processing.

Reads server logs, parses error/user/API/warning entries via regex,
stores aggregated metrics in SQLite with parameterized queries,
and generates an HTML report with error summary, API latency table,
and active session count.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration — all values come from environment variables
# ---------------------------------------------------------------------------

LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """Base type for a parsed log line."""
    timestamp: str
    level: str


@dataclass
class ErrorEntry(LogEntry):
    """An ERROR-level log entry."""
    message: str


@dataclass
class UserEntry(LogEntry):
    """A user session event (login/logout)."""
    user_id: str
    action: str


@dataclass
class ApiCallEntry(LogEntry):
    """An API call with response time."""
    endpoint: str
    duration_ms: int


@dataclass
class WarnEntry(LogEntry):
    """A WARN-level log entry."""
    message: str


# ---------------------------------------------------------------------------
# Regex patterns for log line parsing
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN|WARNING)\s+"
    r"(?P<rest>.*)$"
)

_USER_PATTERN = re.compile(
    r"^User\s+(?P<user_id>\S+)\s+(?P<action>.*)$"
)

_API_PATTERN = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract — read and parse log lines
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: str) -> list[LogEntry]:
    """Read the log file and parse each line into structured entries.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of LogEntry subclass instances (ErrorEntry, UserEntry,
        ApiCallEntry, or WarnEntry).
    """
    entries: list[LogEntry] = []

    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return entries

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp: str = match.group("timestamp")
            level: str = match.group("level")
            rest: str = match.group("rest")

            if level == "ERROR":
                entries.append(ErrorEntry(
                    timestamp=timestamp, level=level, message=rest,
                ))
            elif level == "INFO":
                user_match = _USER_PATTERN.match(rest)
                if user_match:
                    entries.append(UserEntry(
                        timestamp=timestamp, level=level,
                        user_id=user_match.group("user_id"),
                        action=user_match.group("action"),
                    ))
                    continue

                api_match = _API_PATTERN.match(rest)
                if api_match:
                    entries.append(ApiCallEntry(
                        timestamp=timestamp, level=level,
                        endpoint=api_match.group("endpoint"),
                        duration_ms=int(api_match.group("duration") or 0),
                    ))
                    continue
            elif level in ("WARN", "WARNING"):
                entries.append(WarnEntry(
                    timestamp=timestamp, level=level, message=rest,
                ))

    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate parsed entries into summaries
# ---------------------------------------------------------------------------

def transform_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Aggregate error messages into occurrence counts.

    Args:
        entries: Parsed log entries.

    Returns:
        Mapping of error message text to occurrence count.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        if isinstance(entry, ErrorEntry):
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def transform_api_latency(entries: list[LogEntry]) -> dict[str, list[int]]:
    """Group API call durations by endpoint.

    Args:
        entries: Parsed log entries.

    Returns:
        Mapping of endpoint path to list of response times in ms.
    """
    stats: dict[str, list[int]] = {}
    for entry in entries:
        if isinstance(entry, ApiCallEntry):
            stats.setdefault(entry.endpoint, []).append(entry.duration_ms)
    return stats


def transform_active_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """Track user sessions from login/logout events.

    Args:
        entries: Parsed log entries.

    Returns:
        Mapping of user_id to login timestamp for currently active sessions.
    """
    sessions: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, UserEntry):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                del sessions[entry.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load — persist to database and generate report
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Error message to count mapping.
        api_latency: Endpoint to list of response times mapping.
    """
    now: str = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for message, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in api_latency.items():
        avg: float = sum(times) / len(times) if times else 0.0
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Generate an HTML report summarizing errors, API latency, and sessions.

    Args:
        error_counts: Error message to count mapping.
        api_latency: Endpoint to list of response times mapping.
        active_sessions: Currently active user sessions.
        output_path: Path to write the HTML report to.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency.items():
        avg: float = sum(times) / len(times) if times else 0.0
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the Extract → Transform → Load pipeline end-to-end."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    entries: list[LogEntry] = extract_log_entries(LOG_FILE)

    # Transform
    error_counts: dict[str, int] = transform_errors(entries)
    api_latency: dict[str, list[int]] = transform_api_latency(entries)
    active_sessions: dict[str, str] = transform_active_sessions(entries)

    # Load
    load_to_database(DB_PATH, error_counts, api_latency)
    generate_report(error_counts, api_latency, active_sessions)

    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    main()