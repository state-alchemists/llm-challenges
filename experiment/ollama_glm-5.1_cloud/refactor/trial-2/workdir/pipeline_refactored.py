"""Server log processing pipeline.

Extracts log entries, transforms them into structured metrics,
loads results into a database, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, TypedDict


class Metrics(TypedDict):
    """Aggregated metrics produced by the transform step."""
    error_counts: Dict[str, int]
    api_latency: Dict[str, float]
    active_sessions: int

# ---------------------------------------------------------------------------
# Configuration – all values sourced from environment variables with
# sensible defaults so the script runs standalone without configuration.
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A generic log entry with timestamp, level, and message."""

    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with endpoint and latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedLog:
    """Container for all categorised log entries."""

    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------
# Log line format: "2024-01-01 12:00:00 LEVEL rest_of_message"
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(INFO|ERROR|WARN)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


# ---------------------------------------------------------------------------
# ETL: Extract
# ---------------------------------------------------------------------------


def extract(log_file: str) -> ParsedLog:
    """Parse the server log file and categorise entries.

    Uses regex patterns to robustly handle variable log formatting
    instead of fragile string splitting.

    Args:
        log_file: Path to the server log file.

    Returns:
        A ParsedLog with errors, warnings, user events, and API calls.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_file):
        return parsed

    with open(log_file, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp: str = match.group(1)
            level: str = match.group(2)
            remainder: str = match.group(3)

            if level == "ERROR":
                parsed.errors.append(LogEntry(timestamp, level, remainder))

            elif level == "WARN":
                parsed.warnings.append(LogEntry(timestamp, level, remainder))

            elif level == "INFO":
                user_match = USER_PATTERN.match(remainder)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2)
                    parsed.user_events.append(
                        UserEvent(timestamp, uid, action)
                    )
                    continue

                api_match = API_PATTERN.match(remainder)
                if api_match:
                    endpoint = api_match.group(1)
                    duration = int(api_match.group(2)) if api_match.group(2) else 0
                    parsed.api_calls.append(
                        ApiCall(timestamp, endpoint, duration)
                    )

    return parsed


# ---------------------------------------------------------------------------
# ETL: Transform
# ---------------------------------------------------------------------------


def transform(parsed: ParsedLog) -> Metrics:
    """Aggregate parsed log data into summary metrics.

    Computes error occurrence counts, per-endpoint average API latency,
    and the number of currently active sessions.

    Args:
        parsed: The extracted log data.

    Returns:
        A dict with keys 'error_counts', 'api_latency',
        and 'active_sessions'.
    """
    # Aggregate error counts
    error_counts: Dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # Compute per-endpoint average latency
    api_latency: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.duration_ms)

    api_avg: Dict[str, float] = {}
    for endpoint, times in api_latency.items():
        api_avg[endpoint] = round(sum(times) / len(times), 1)

    # Track active sessions (logged in minus logged out)
    active_sessions: Dict[str, str] = {}
    for event in parsed.user_events:
        if "logged in" in event.action:
            active_sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in active_sessions:
            active_sessions.pop(event.user_id)

    return {
        "error_counts": error_counts,
        "api_latency": api_avg,
        "active_sessions": len(active_sessions),
    }


# ---------------------------------------------------------------------------
# ETL: Load
# ---------------------------------------------------------------------------


def load(metrics: Metrics, db_path: str) -> None:
    """Persist aggregated metrics into the SQLite database.

    Uses parameterized queries to prevent SQL injection.

    Args:
        metrics: The transformed metrics dict.
        db_path: Path to the SQLite database file.
    """
    error_counts: Dict[str, int] = metrics["error_counts"]
    api_latency: Dict[str, float] = metrics["api_latency"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now: str = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(metrics: Metrics, output_path: str) -> None:
    """Write an HTML report summarising the pipeline results.

    The report contains three sections matching the original output:
    error summary, API latency table, and active session count.

    Args:
        metrics: The transformed metrics dict.
        output_path: File path for the generated HTML report.
    """
    error_counts: Dict[str, int] = metrics["error_counts"]
    api_latency: Dict[str, float] = metrics["api_latency"]
    active_sessions: int = metrics["active_sessions"]

    html_parts: List[str] = []
    html_parts.append("<html>")
    html_parts.append("<head><title>System Report</title></head>")
    html_parts.append("<body>")

    # Error summary
    html_parts.append("<h1>Error Summary</h1>")
    html_parts.append("<ul>")
    for err_msg, count in error_counts.items():
        html_parts.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    html_parts.append("</ul>")

    # API latency table
    html_parts.append("<h2>API Latency</h2>")
    html_parts.append("<table border='1'>")
    html_parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg_ms in api_latency.items():
        html_parts.append(f"<tr><td>{endpoint}</td><td>{avg_ms}</td></tr>")
    html_parts.append("</table>")

    # Active sessions
    html_parts.append("<h2>Active Sessions</h2>")
    html_parts.append(f"<p>{active_sessions} user(s) currently active</p>")

    html_parts.append("</body>")
    html_parts.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(html_parts))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed = extract(LOG_FILE)
    metrics = transform(parsed)
    load(metrics, DB_PATH)
    generate_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()