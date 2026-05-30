"""Server-log pipeline: extract, transform, and load log data into a report.

Reads a server log file, parses structured entries (errors, user sessions,
API calls, warnings), aggregates them, persists metrics to SQLite via
parameterized queries, and writes an HTML report.
"""

import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration — all values come from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A parsed ERROR log line."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A parsed user login/logout log line."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """A parsed API latency log line."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarningEntry:
    """A parsed WARN log line."""
    timestamp: str
    message: str


@dataclass
class LogData:
    """Aggregated result of log extraction."""
    errors: List[ErrorEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[WarningEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns for robust log-line parsing
# ---------------------------------------------------------------------------

# General log-line: "2024-01-01 12:00:00 LEVEL ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN|DEBUG)\s+"
    r"(?P<rest>.*)$"
)

# "User <id> <action>"
_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# "API <endpoint> took <n>ms"
_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$"
)


# ---------------------------------------------------------------------------
# Extract — read raw log lines and parse into structured data
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: str) -> LogData:
    """Parse server log file into structured LogData.

    Args:
        log_path: Path to the server log file.

    Returns:
        A LogData instance containing parsed errors, user events,
        API calls, and warnings.
    """
    data: LogData = LogData()
    if not os.path.exists(log_path):
        return data

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp: str = match.group("timestamp")
            level: str = match.group("level")
            rest: str = match.group("rest")

            if level == "ERROR":
                data.errors.append(ErrorEntry(timestamp=timestamp, message=rest))

            elif level == "WARN":
                data.warnings.append(WarningEntry(timestamp=timestamp, message=rest))

            elif level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    data.user_events.append(UserEvent(
                        timestamp=timestamp,
                        user_id=user_match.group("user_id"),
                        action=user_match.group("action"),
                    ))
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    data.api_calls.append(ApiCall(
                        timestamp=timestamp,
                        endpoint=api_match.group("endpoint"),
                        duration_ms=int(api_match.group("duration")),
                    ))

    return data


# ---------------------------------------------------------------------------
# Transform — aggregate parsed data into summary statistics
# ---------------------------------------------------------------------------

def transform_log_data(data: LogData) -> dict:
    """Aggregate extracted log data into summary statistics.

    Computes error frequency counts, per-endpoint API latency averages,
    and the set of currently active user sessions.

    Args:
        data: Parsed LogData from extraction.

    Returns:
        A dict with keys 'error_counts', 'api_latency', and
        'active_sessions'.
    """
    # Error frequency
    error_counts: Dict[str, int] = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # API latency averages
    endpoint_times: Dict[str, List[int]] = defaultdict(list)
    for call in data.api_calls:
        endpoint_times[call.endpoint].append(call.duration_ms)

    api_latency: Dict[str, float] = {}
    for endpoint, times in endpoint_times.items():
        api_latency[endpoint] = round(sum(times) / len(times), 1)

    # Active sessions — users who logged in but haven't logged out
    sessions: Dict[str, str] = {}
    for event in data.user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)

    return {
        "error_counts": error_counts,
        "api_latency": api_latency,
        "active_sessions": len(sessions),
    }


# ---------------------------------------------------------------------------
# Load — persist to database and write HTML report
# ---------------------------------------------------------------------------

def load_to_database(
    stats: dict,
    db_path: str,
    db_host: str,
    db_port: str,
    db_user: str,
) -> None:
    """Insert aggregated metrics into SQLite using parameterized queries.

    Args:
        stats: Aggregated statistics from transform_log_data.
        db_path: Path to the SQLite database file.
        db_host: Database host (logged for traceability).
        db_port: Database port (logged for traceability).
        db_user: Database user (logged for traceability).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now: str = str(datetime.now())

    for msg, count in stats["error_counts"].items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in stats["api_latency"].items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def load_report(stats: dict, output_path: str) -> None:
    """Render and write the HTML report.

    The report contains three sections: Error Summary, API Latency,
    and Active Sessions — matching the format of the original pipeline.

    Args:
        stats: Aggregated statistics from transform_log_data.
        output_path: File path for the generated report.
    """
    parts: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in stats["error_counts"].items():
        parts.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    parts.append("</ul>")
    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, avg_ms in stats["api_latency"].items():
        parts.append(f"<tr><td>{endpoint}</td><td>{avg_ms}</td></tr>")

    parts.append("</table>")
    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{stats['active_sessions']} user(s) currently active</p>")
    parts.append("</body>")
    parts.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    # Ensure the log fixture exists when running standalone
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    data: LogData = extract_log_entries(LOG_FILE)

    # Transform
    stats: dict = transform_log_data(data)

    # Load
    load_to_database(stats, DB_PATH, DB_HOST, DB_PORT, DB_USER)
    load_report(stats, "report.html")

    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    main()