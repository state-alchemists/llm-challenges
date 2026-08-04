"""Server-log processing pipeline: Extract → Transform → Load.

Reads server logs, parses structured records, persists metrics to SQLite,
and produces an HTML report summarising errors, API latency, and active
sessions.  All configuration is read from environment variables so that no
credentials or paths are hard-coded.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration – every value comes from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("PIPELINE_LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("PIPELINE_REPORT_PATH", "report.html")

DB_HOST: str = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.getenv("PIPELINE_DB_PASS", "")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r"\s+"
    r"(?P<level>INFO|ERROR|WARN)"
    r"\s+"
    r"(?P<rest>.*)"
)

USER_PATTERN = re.compile(
    r"User\s+(?P<uid>\S+)\s+(?P<action>.*)"
)

API_PATTERN = re.compile(
    r"API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?"
)


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A user login / logout event."""
    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCall:
    """An API call with endpoint and latency in milliseconds."""
    timestamp: str
    endpoint: str
    ms: int


@dataclass
class ParsedLog:
    """Aggregation of all structured data extracted from the log file."""
    errors: list[LogEntry] = field(default_factory=list)
    warnings: list[LogEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(log_path: str) -> ParsedLog:
    """Read the log file and parse each line into structured records.

    Uses regex-based parsing instead of fragile ``str.split`` so that
    messages containing spaces are captured correctly.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ``ParsedLog`` with all recognised records.
    """
    parsed = ParsedLog()
    path = Path(log_path)

    if not path.exists():
        print(f"Log file not found: {log_path}")
        return parsed

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                parsed.errors.append(
                    LogEntry(timestamp=timestamp, level=level, message=rest)
                )
            elif level == "WARN":
                parsed.warnings.append(
                    LogEntry(timestamp=timestamp, level=level, message=rest)
                )
            elif level == "INFO":
                user_match = USER_PATTERN.match(rest)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            uid=user_match.group("uid"),
                            action=user_match.group("action").strip(),
                        )
                    )
                    continue

                api_match = API_PATTERN.match(rest)
                if api_match:
                    ms_str = api_match.group("ms") or "0"
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            ms=int(ms_str),
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(parsed: ParsedLog) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """Aggregate raw records into report-ready summaries.

    Args:
        parsed: The extracted log data.

    Returns:
        A triple of:
        - ``error_counts``: mapping error message → occurrence count.
        - ``api_latency``: mapping endpoint → list of latencies in ms.
        - ``active_sessions``: number of currently logged-in users.
    """
    # Error summary
    error_counts: dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # API latency buckets
    api_latency: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.ms)

    # Active session tracking: login adds, logout removes
    sessions: set[str] = set()
    for event in parsed.user_events:
        if "logged in" in event.action:
            sessions.add(event.uid)
        elif "logged out" in event.action:
            sessions.discard(event.uid)

    return error_counts, api_latency, len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """Persist aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message → count.
        api_latency: Mapping of endpoint → list of latencies.
    """
    now = datetime.datetime.now().isoformat()

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Error rows — parameterised, no string formatting
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    # API latency rows — parameterised
    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def load_report(
    report_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """Write the HTML report to disk.

    Args:
        report_path: Destination file path for the HTML report.
        error_counts: Mapping of error message → count.
        api_latency: Mapping of endpoint → list of latencies.
        active_sessions: Number of currently active sessions.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # --- Error Summary ---
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    # --- API Latency ---
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    # --- Active Sessions ---
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    Path(report_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Reads config from environment variables, parses the log file,
    computes aggregates, persists to SQLite, and writes the HTML report.
    """
    parsed = extract(LOG_FILE)
    error_counts, api_latency, active_sessions = transform(parsed)
    load_to_db(DB_PATH, error_counts, api_latency)
    load_report(REPORT_PATH, error_counts, api_latency, active_sessions)
    print(f"Pipeline finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Sample data for local testing
# ---------------------------------------------------------------------------

SAMPLE_LOG_LINES: list[str] = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


if __name__ == "__main__":
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text("\n".join(SAMPLE_LOG_LINES) + "\n", encoding="utf-8")
    run_pipeline()