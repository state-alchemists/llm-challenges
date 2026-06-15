"""ETL pipeline: parse server logs, load metrics to SQLite, generate HTML report."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Config loaded from environment variables
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class ErrorEntry:
    """An ERROR-level log entry."""
    timestamp: str
    message: str


@dataclass
class WarnEntry:
    """A WARN-level log entry."""
    timestamp: str
    message: str


@dataclass
class UserEntry:
    """An INFO-level user action log entry."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEntry:
    """An INFO-level API latency log entry."""
    timestamp: str
    endpoint: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
_BASE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.*)$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def extract(log_file_path: str) -> Tuple[List[object], Dict[str, str]]:
    """Parse the server log and return structured entries plus active sessions.

    Args:
        log_file_path: Path to the log file to read.

    Returns:
        A tuple of (entries, sessions) where entries is a list of parsed log
        record objects and sessions is a mapping of user_id -> login timestamp
        for users currently logged in.
    """
    entries: List[object] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file_path):
        return entries, sessions

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _BASE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                entries.append(ErrorEntry(timestamp=timestamp, message=rest))

            elif level == "WARN":
                entries.append(WarnEntry(timestamp=timestamp, message=rest))

            elif level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    user_id = user_match.group("user_id")
                    action = user_match.group("action")
                    entries.append(
                        UserEntry(timestamp=timestamp, user_id=user_id, action=action)
                    )
                    if "logged in" in action:
                        sessions[user_id] = timestamp
                    elif "logged out" in action and user_id in sessions:
                        sessions.pop(user_id)
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    entries.append(
                        ApiEntry(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration")),
                        )
                    )

    return entries, sessions


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
@dataclass
class TransformedData:
    """Aggregates produced from the extracted log entries."""
    error_counts: Dict[str, int]
    api_latency: Dict[str, List[int]]
    active_sessions: Dict[str, str]


def transform(entries: List[object], sessions: Dict[str, str]) -> TransformedData:
    """Aggregate errors and API latencies from parsed log entries.

    Args:
        entries: List of parsed log record objects.
        sessions: Mapping of currently active user sessions.

    Returns:
        TransformedData containing error counts, API latencies, and sessions.
    """
    error_counts: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif isinstance(entry, ApiEntry):
            api_latency.setdefault(entry.endpoint, []).append(entry.duration_ms)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=sessions,
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load(data: TransformedData, db_path: str) -> None:
    """Persist aggregates to SQLite and write ``report.html``.

    Args:
        data: Aggregated metrics to store.
        db_path: Path to the SQLite database file.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in data.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in data.api_latency.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    _write_report(data)
    print(f"Job finished at {datetime.datetime.now()}")


def _write_report(data: TransformedData) -> None:
    """Generate ``report.html`` from the transformed data."""
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, times in data.api_latency.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    active_count = len(data.active_sessions)
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open("report.html", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    """Execute the full ETL pipeline."""
    if not os.path.exists(LOG_FILE):
        _seed_log_file(LOG_FILE)

    entries, sessions = extract(LOG_FILE)
    data = transform(entries, sessions)
    load(data, DB_PATH)


def _seed_log_file(log_file_path: str) -> None:
    """Create a sample log file for demonstration purposes."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.writelines(sample_lines)


if __name__ == "__main__":
    run_pipeline()
