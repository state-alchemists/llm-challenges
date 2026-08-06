"""Refactored log-processing pipeline.

Extracts server log events, transforms them into aggregated metrics,
and loads the results into an SQLite database and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str
    raw_message: str


@dataclass
class UserEvent:
    """A user login/logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API endpoint call with latency."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedData:
    """Container for all extracted log data."""
    errors: list[LogEntry] = field(default_factory=list)
    warnings: list[LogEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)


def get_config() -> dict[str, str]:
    """Return configuration values sourced from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def extract(log_file_path: str) -> ParsedData:
    """Parse the server log file and return structured data.

    Args:
        log_file_path: Path to the log file to parse.

    Returns:
        ParsedData containing errors, warnings, user events, and API calls.
    """
    data = ParsedData()

    if not os.path.exists(log_file_path):
        return data

    line_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
    )
    user_pattern = re.compile(r"^User (\d+) (.+)$")
    api_pattern = re.compile(r"^API (\S+) took (\d+)ms$")

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = line_pattern.match(line)
            if not match:
                continue

            timestamp, level, message = match.groups()

            if level == "ERROR":
                data.errors.append(LogEntry(timestamp, level, message))
            elif level == "WARN":
                data.warnings.append(LogEntry(timestamp, level, message))
            elif level == "INFO":
                user_match = user_pattern.match(message)
                if user_match:
                    user_id, action = user_match.groups()
                    data.user_events.append(UserEvent(timestamp, user_id, action))
                else:
                    api_match = api_pattern.match(message)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        data.api_calls.append(
                            ApiCall(timestamp, endpoint, int(duration))
                        )

    return data


def transform(
    data: ParsedData,
) -> tuple[dict[str, int], dict[str, float], dict[str, str]]:
    """Transform extracted data into aggregated metrics and active sessions.

    Args:
        data: The ParsedData from the extract step.

    Returns:
        A tuple of (error_counts, api_averages, active_sessions).
    """
    error_counts: dict[str, int] = {}
    for entry in data.errors:
        error_counts[entry.raw_message] = error_counts.get(entry.raw_message, 0) + 1

    api_stats: dict[str, list[int]] = {}
    for call in data.api_calls:
        api_stats.setdefault(call.endpoint, []).append(call.duration_ms)

    api_averages: dict[str, float] = {}
    for endpoint, times in api_stats.items():
        api_averages[endpoint] = sum(times) / len(times)

    active_sessions: dict[str, str] = {}
    for event in data.user_events:
        if "logged in" in event.action:
            active_sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in active_sessions:
            active_sessions.pop(event.user_id)

    return error_counts, api_averages, active_sessions


def load(
    db_path: str,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
) -> None:
    """Load aggregated metrics into the SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message to occurrence count.
        api_averages: Mapping of endpoint to average latency in milliseconds.
    """
    print("Connecting to database...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg in api_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    active_sessions: dict[str, str],
) -> str:
    """Generate an HTML report string from the aggregated metrics.

    Args:
        error_counts: Mapping of error message to occurrence count.
        api_averages: Mapping of endpoint to average latency in milliseconds.
        active_sessions: Mapping of active user IDs to their login timestamps.

    Returns:
        A complete HTML document as a string.
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

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in api_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = get_config()

    if not os.path.exists(config["log_file"]):
        with open(config["log_file"], "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    data = extract(config["log_file"])
    error_counts, api_averages, active_sessions = transform(data)
    load(config["db_path"], error_counts, api_averages)

    report_html = generate_report(error_counts, api_averages, active_sessions)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(report_html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
