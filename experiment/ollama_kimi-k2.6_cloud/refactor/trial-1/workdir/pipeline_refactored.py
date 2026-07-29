"""Server log ETL pipeline.

Extracts events from a server log file, aggregates metrics, persists them
to SQLite, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _env(key: str, default: str) -> str:
    """Read an environment variable, falling back to *default*."""
    return os.environ.get(key, default)


DB_PATH: str = _env("DB_PATH", "metrics.db")
LOG_FILE: str = _env("LOG_FILE", "server.log")
DB_HOST: str = _env("DB_HOST", "localhost")
DB_PORT: int = int(_env("DB_PORT", "5432"))
DB_USER: str = _env("DB_USER", "admin")
DB_PASS: str = _env("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class LogEvent:
    """A single parsed log line."""

    timestamp: datetime.datetime
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class PipelineResult:
    """Aggregated data ready for load and reporting."""

    error_counts: dict[str, int] = field(default_factory=dict)
    api_stats: dict[str, float] = field(default_factory=dict)
    active_sessions: dict[str, datetime.datetime] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<rest>.*)$"
)

_USER_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<dur>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_logs(log_path: str) -> list[LogEvent]:
    """Parse *log_path* into a list of :class:`LogEvent`.

    Returns an empty list when the file does not exist.
    """
    events: list[LogEvent] = []
    if not os.path.exists(log_path):
        return events

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            ts_str = f"{match['date']} {match['time']}"
            timestamp = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            level = match["level"]
            rest = match["rest"]

            event = LogEvent(timestamp=timestamp, level=level, message=rest)

            if level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    event.user_id = user_match["uid"]
                    event.action = user_match["action"]

                api_match = _API_RE.match(rest)
                if api_match:
                    event.endpoint = api_match["endpoint"]
                    event.duration_ms = int(api_match["dur"]) if api_match["dur"] else 0

            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_events(events: list[LogEvent]) -> PipelineResult:
    """Aggregate *events* into error counts, API latency averages, and session state."""
    result = PipelineResult()
    endpoint_times: dict[str, list[int]] = defaultdict(list)

    for event in events:
        if event.level == "ERROR":
            result.error_counts[event.message] = (
                result.error_counts.get(event.message, 0) + 1
            )

        elif event.level == "INFO" and event.user_id and event.action:
            if "logged in" in event.action:
                result.active_sessions[event.user_id] = event.timestamp
            elif "logged out" in event.action and event.user_id in result.active_sessions:
                del result.active_sessions[event.user_id]

        elif event.level == "INFO" and event.endpoint is not None:
            ms = event.duration_ms if event.duration_ms is not None else 0
            endpoint_times[event.endpoint].append(ms)

    for ep, times in endpoint_times.items():
        result.api_stats[ep] = sum(times) / len(times)

    return result


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_metrics(db_path: str, data: PipelineResult) -> None:
    """Persist aggregated *data* to the SQLite database at *db_path*.

    Uses parameterized queries to avoid SQL injection.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat()

        for message, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, message, count),
            )

        for endpoint, avg_ms in data.api_stats.items():
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(data: PipelineResult, output_path: str) -> None:
    """Write an HTML report of *data* to *output_path*."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for endpoint, avg_ms in data.api_stats.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{len(data.active_sessions)} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full ETL pipeline."""
    if not os.path.exists(LOG_FILE):
        _write_sample_log(LOG_FILE)

    events = extract_logs(LOG_FILE)
    data = transform_events(events)
    load_metrics(DB_PATH, data)
    generate_report(data, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


def _write_sample_log(log_path: str) -> None:
    """Create a sample log file at *log_path* for demonstration."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.writelines(sample_lines)


if __name__ == "__main__":
    main()
