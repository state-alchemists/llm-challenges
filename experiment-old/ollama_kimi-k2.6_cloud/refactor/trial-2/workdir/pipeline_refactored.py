"""Server log pipeline: extract, transform, load, and report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: str = "report.html"


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults."""
    return Config(
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        log_file=os.environ.get("LOG_FILE", "server.log"),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_user=os.environ.get("DB_USER", "admin"),
        db_pass=os.environ.get("DB_PASS", "password123"),
    )


@dataclass
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class WarnEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


@dataclass
class UserAction:
    """A parsed user login/logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """A parsed API latency event."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedLogs:
    """Container for all structured log records."""

    errors: list[ErrorEntry] = field(default_factory=list)
    warnings: list[WarnEntry] = field(default_factory=list)
    user_actions: list[UserAction] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)


# Regex for the common log prefix: TIMESTAMP LEVEL remainder
_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<rest>.*)$"
)

# Regex for user session lines: User <id> <action>
_USER_PATTERN = re.compile(r"^User (?P<user_id>\S+) (?P<action>.*)$")

# Regex for API latency lines: API <endpoint> took <duration>ms
_API_PATTERN = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


def extract(log_file: str) -> list[str]:
    """Read non-empty lines from the log file.

    Args:
        log_file: Path to the server log.

    Returns:
        A list of stripped, non-empty log lines.
    """
    if not os.path.exists(log_file):
        return []
    with open(log_file, "r") as f:
        return [line.strip() for line in f if line.strip()]


def transform(lines: list[str]) -> ParsedLogs:
    """Parse raw log lines into structured records using regex.

    Args:
        lines: Raw log lines from the extract phase.

    Returns:
        A ``ParsedLogs`` dataclass holding categorized records.
    """
    parsed = ParsedLogs()
    for line in lines:
        match = _LOG_PATTERN.match(line)
        if not match:
            continue

        timestamp = match.group("timestamp")
        level = match.group("level")
        rest = match.group("rest")

        if level == "ERROR":
            parsed.errors.append(ErrorEntry(timestamp=timestamp, message=rest))
        elif level == "WARN":
            parsed.warnings.append(WarnEntry(timestamp=timestamp, message=rest))
        elif level == "INFO":
            user_match = _USER_PATTERN.match(rest)
            if user_match:
                parsed.user_actions.append(
                    UserAction(
                        timestamp=timestamp,
                        user_id=user_match.group("user_id"),
                        action=user_match.group("action"),
                    )
                )
            else:
                api_match = _API_PATTERN.match(rest)
                if api_match:
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration")),
                        )
                    )
    return parsed


def compute_error_counts(errors: list[ErrorEntry]) -> dict[str, int]:
    """Aggregate error occurrences by message text.

    Args:
        errors: Parsed ERROR entries.

    Returns:
        Mapping from error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def compute_api_latency(api_calls: list[ApiCall]) -> dict[str, float]:
    """Calculate average latency per API endpoint.

    Args:
        api_calls: Parsed API call entries.

    Returns:
        Mapping from endpoint path to average duration in milliseconds.
    """
    endpoint_times: dict[str, list[int]] = defaultdict(list)
    for call in api_calls:
        endpoint_times[call.endpoint].append(call.duration_ms)
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }


def compute_active_sessions(user_actions: list[UserAction]) -> dict[str, str]:
    """Track currently active sessions from login/logout events.

    Args:
        user_actions: Parsed user action entries.

    Returns:
        Mapping from user ID to the timestamp of their latest login.
    """
    sessions: dict[str, str] = {}
    for action in user_actions:
        if "logged in" in action.action:
            sessions[action.user_id] = action.timestamp
        elif "logged out" in action.action and action.user_id in sessions:
            sessions.pop(action.user_id)
    return sessions


def load_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Aggregated error counts.
        api_latency: Aggregated API latency averages.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())
    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: dict[str, str],
    report_path: str,
) -> None:
    """Write an HTML report with error summary, API latency, and active sessions.

    Args:
        error_counts: Aggregated error counts.
        api_latency: Aggregated API latency averages.
        active_sessions: Currently active user sessions.
        report_path: Destination path for the HTML report.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg_ms in api_latency.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = load_config()
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    raw_lines = extract(config.log_file)
    parsed = transform(raw_lines)

    error_counts = compute_error_counts(parsed.errors)
    api_latency = compute_api_latency(parsed.api_calls)
    active_sessions = compute_active_sessions(parsed.user_actions)

    load_db(config.db_path, error_counts, api_latency)
    generate_report(error_counts, api_latency, active_sessions, config.report_path)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = load_config()
    if not os.path.exists(config.log_file):
        with open(config.log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
