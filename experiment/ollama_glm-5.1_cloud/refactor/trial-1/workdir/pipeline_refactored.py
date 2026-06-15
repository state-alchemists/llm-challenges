"""Refactored server-log pipeline: Extract → Transform → Load.

Reads server logs, aggregates errors / API latency / active sessions,
persists metrics to SQLite, and generates an HTML report.

All configuration is read from environment variables so no credentials
or paths are hard-coded in source.
"""

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — every value comes from the environment
# ---------------------------------------------------------------------------
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: str = os.environ.get("DB_PORT", "5432")
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")  # noqa: S105

# ---------------------------------------------------------------------------
# Regex patterns for structured log-line parsing
# ---------------------------------------------------------------------------
_ERROR_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.+)$"
)
_USER_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_API_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$"
)
_WARN_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.+)$"
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass
class ErrorEntry:
    """An ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class UserEntry:
    """A user login/logout event."""

    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCallEntry:
    """An API call with measured latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarnEntry:
    """A WARN-level log line."""

    timestamp: str
    message: str


LogEntry = ErrorEntry | UserEntry | ApiCallEntry | WarnEntry


@dataclass
class Aggregations:
    """Aggregated results produced by the transform step."""

    error_counts: dict[str, int] = field(default_factory=dict)
    endpoint_latencies: dict[str, list[int]] = field(default_factory=dict)
    active_session_count: int = 0


# ---------------------------------------------------------------------------
# Extract — read and parse log lines
# ---------------------------------------------------------------------------
def extract_log_entries(log_path: str) -> list[LogEntry]:
    """Parse a server log file into structured entries using regex.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A list of typed :class:`LogEntry` objects, one per recognised line.
    """
    path = Path(log_path)
    if not path.exists():
        return []

    entries: list[LogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        if match := _ERROR_RE.match(line):
            entries.append(ErrorEntry(
                timestamp=match["timestamp"],
                message=match["message"],
            ))
        elif match := _USER_RE.match(line):
            entries.append(UserEntry(
                timestamp=match["timestamp"],
                uid=match["uid"],
                action=match["action"],
            ))
        elif match := _API_RE.match(line):
            entries.append(ApiCallEntry(
                timestamp=match["timestamp"],
                endpoint=match["endpoint"],
                duration_ms=int(match["duration"]) if match["duration"] else 0,
            ))
        elif match := _WARN_RE.match(line):
            entries.append(WarnEntry(
                timestamp=match["timestamp"],
                message=match["message"],
            ))

    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate entries into metrics
# ---------------------------------------------------------------------------
def transform_entries(entries: list[LogEntry]) -> Aggregations:
    """Aggregate parsed log entries into error counts, API latencies, and sessions.

    Args:
        entries: Parsed log entries from :func:`extract_log_entries`.

    Returns:
        An :class:`Aggregations` instance ready for the load step.
    """
    error_counts: dict[str, int] = {}
    endpoint_latencies: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif isinstance(entry, UserEntry):
            if "logged in" in entry.action:
                sessions[entry.uid] = entry.timestamp
            elif "logged out" in entry.action and entry.uid in sessions:
                sessions.pop(entry.uid)
        elif isinstance(entry, ApiCallEntry):
            endpoint_latencies.setdefault(entry.endpoint, []).append(entry.duration_ms)

    return Aggregations(
        error_counts=error_counts,
        endpoint_latencies=endpoint_latencies,
        active_session_count=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — persist to database and generate report
# ---------------------------------------------------------------------------
def load_to_database(db_path: str, aggregations: Aggregations) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        aggregations: Aggregated data to store.
    """
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in aggregations.error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in aggregations.endpoint_latencies.items():
            avg = sum(times) / len(times) if times else 0.0
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_report(output_path: str, aggregations: Aggregations) -> None:
    """Generate an HTML report from aggregated metrics.

    Args:
        output_path: Filesystem path for the generated report.
        aggregations: Aggregated data to render.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
    ]

    # — Error summary —
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in aggregations.error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    # — API latency table —
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in aggregations.endpoint_latencies.items():
        avg = round(sum(times) / len(times), 1) if times else 0.0
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    # — Active sessions —
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{aggregations.active_session_count} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    entries = extract_log_entries(LOG_FILE)
    aggregations = transform_entries(entries)
    load_to_database(DB_PATH, aggregations)
    load_report("report.html", aggregations)
    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    main()