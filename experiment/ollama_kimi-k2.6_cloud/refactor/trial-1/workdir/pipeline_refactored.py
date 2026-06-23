"""Server log ETL pipeline.

Extracts log entries from a server log file, transforms them into
aggregated metrics, and loads the results into SQLite and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserAction:
    """A user login/logout event extracted from a log line."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call event extracted from a log line."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedData:
    """Container for all entries extracted from the log file."""
    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    user_actions: List[UserAction] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)


@dataclass
class TransformedData:
    """Aggregated metrics and session state produced by the transform step."""
    error_counts: Dict[str, int]
    api_latency: Dict[str, float]
    active_sessions: Dict[str, str]


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<message>.*)$"
)

USER_PATTERN = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")
API_PATTERN = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def get_config() -> Config:
    """Load configuration from environment variables.

    Falls back to the defaults used by the legacy script.
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


def extract(log_path: str) -> ParsedData:
    """Parse a server log file into structured entries.

    Args:
        log_path: Path to the log file to read.

    Returns:
        A :class:`ParsedData` object containing errors, warnings, user
        actions, and API calls discovered in the file.
    """
    data = ParsedData()
    if not os.path.exists(log_path):
        return data

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            message = match.group("message")

            if level == "ERROR":
                data.errors.append(
                    LogEntry(timestamp=timestamp, level=level, message=message)
                )
            elif level == "WARN":
                data.warnings.append(
                    LogEntry(timestamp=timestamp, level=level, message=message)
                )
            elif level == "INFO":
                user_match = USER_PATTERN.match(message)
                if user_match:
                    data.user_actions.append(
                        UserAction(
                            timestamp=timestamp,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = API_PATTERN.match(message)
                if api_match:
                    duration_str = api_match.group("duration")
                    data.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(duration_str) if duration_str else 0,
                        )
                    )

    return data


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(data: ParsedData) -> TransformedData:
    """Aggregate parsed log entries into metrics and session state.

    Args:
        data: The raw parsed data produced by :func:`extract`.

    Returns:
        Aggregated error counts, per-endpoint API latency averages, and the
        current active-session map.
    """
    error_counts: Dict[str, int] = {}
    for entry in data.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    api_times: Dict[str, List[int]] = {}
    for call in data.api_calls:
        api_times.setdefault(call.endpoint, []).append(call.duration_ms)

    api_latency: Dict[str, float] = {
        endpoint: sum(times) / len(times)
        for endpoint, times in api_times.items()
    }

    active_sessions: Dict[str, str] = {}
    for action in data.user_actions:
        if "logged in" in action.action:
            active_sessions[action.user_id] = action.timestamp
        elif "logged out" in action.action and action.user_id in active_sessions:
            active_sessions.pop(action.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=active_sessions,
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    """Create required tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def _write_errors(conn: sqlite3.Connection, error_counts: Dict[str, int]) -> None:
    """Persist aggregated error counts using parameterized queries."""
    now = datetime.datetime.now().isoformat()
    for message, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, message, count),
        )


def _write_api_metrics(
    conn: sqlite3.Connection, api_latency: Dict[str, float]
) -> None:
    """Persist aggregated API latency using parameterized queries."""
    now = datetime.datetime.now().isoformat()
    for endpoint, avg_ms in api_latency.items():
        conn.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )


def _generate_report(
    error_counts: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions: Dict[str, str],
) -> str:
    """Build the HTML report string from transformed data."""
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])
    for endpoint, avg in api_latency.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines)


def load(
    db_path: str,
    error_counts: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions: Dict[str, str],
) -> None:
    """Load metrics into the database and write the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message to occurrence count.
        api_latency: Mapping of API endpoint to average latency in ms.
        active_sessions: Mapping of active user IDs to their login timestamp.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        _write_errors(conn, error_counts)
        _write_api_metrics(conn, api_latency)
        conn.commit()
    finally:
        conn.close()

    report = _generate_report(error_counts, api_latency, active_sessions)
    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write(report)


# ---------------------------------------------------------------------------
# Bootstrap / main
# ---------------------------------------------------------------------------

def _write_sample_log(log_path: str) -> None:
    """Create a sample log file if none exists."""
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


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = get_config()
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    if not os.path.exists(config.log_file):
        _write_sample_log(config.log_file)

    raw = extract(config.log_file)
    transformed = transform(raw)
    load(
        config.db_path,
        transformed.error_counts,
        transformed.api_latency,
        transformed.active_sessions,
    )
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
