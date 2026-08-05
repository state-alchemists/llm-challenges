"""Refactored log processing pipeline.

Extracts server log events, transforms them into aggregates, and loads
the results into a SQLite database plus an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


LOG_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.+)$"
)

USER_PATTERN = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
API_PATTERN = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")


@dataclass
class ParsedData:
    """Container for extracted log events."""
    errors: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)
    user_actions: List[Tuple[str, str, str]] = field(default_factory=list)
    api_calls: List[Tuple[str, str, int]] = field(default_factory=list)


def get_config() -> Dict[str, str]:
    """Load configuration from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def extract(log_file_path: str) -> ParsedData:
    """Parse the server log and return structured events."""
    data = ParsedData()

    if not os.path.exists(log_file_path):
        return data

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_PATTERN.match(line.strip())
            if not match:
                continue

            timestamp = f"{match.group('date')} {match.group('time')}"
            level = match.group("level")
            message = match.group("message")

            if level == "ERROR":
                data.errors.append((timestamp, message))
            elif level == "WARN":
                data.warnings.append((timestamp, message))
            elif level == "INFO":
                user_match = USER_PATTERN.match(message)
                if user_match:
                    data.user_actions.append((
                        timestamp,
                        user_match.group("user_id"),
                        user_match.group("action"),
                    ))
                else:
                    api_match = API_PATTERN.match(message)
                    if api_match:
                        duration = int(api_match.group("duration") or 0)
                        data.api_calls.append((
                            timestamp,
                            api_match.group("endpoint"),
                            duration,
                        ))

    return data


def transform(data: ParsedData) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Aggregate extracted events into summary statistics."""
    error_counts: Dict[str, int] = {}
    for _, message in data.errors:
        error_counts[message] = error_counts.get(message, 0) + 1

    api_latencies: Dict[str, List[int]] = {}
    for _, endpoint, duration in data.api_calls:
        api_latencies.setdefault(endpoint, []).append(duration)

    active_sessions: Dict[str, str] = {}
    for timestamp, user_id, action in data.user_actions:
        if "logged in" in action:
            active_sessions[user_id] = timestamp
        elif "logged out" in action and user_id in active_sessions:
            active_sessions.pop(user_id)

    return error_counts, api_latencies, active_sessions


def load(
    db_path: str,
    db_host: str,
    db_port: str,
    db_user: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Persist aggregates to the database and generate the HTML report."""
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

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
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, durations in api_latencies.items():
        avg = sum(durations) / len(durations)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()

    generate_report(error_counts, api_latencies, active_sessions)


def generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Write report.html with error summary, API latency, and active sessions."""
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

    for ep, durations in api_latencies.items():
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open("report.html", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def create_sample_log_file(log_file_path: str) -> None:
    """Create a sample log file if none exists."""
    if os.path.exists(log_file_path):
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]

    with open(log_file_path, "w", encoding="utf-8") as f:
        for line in sample_lines:
            f.write(line + "\n")


def run_pipeline() -> None:
    """Orchestrate the Extract -> Transform -> Load pipeline."""
    config = get_config()

    create_sample_log_file(config["log_file"])

    data = extract(config["log_file"])
    error_counts, api_latencies, active_sessions = transform(data)
    load(
        db_path=config["db_path"],
        db_host=config["db_host"],
        db_port=config["db_port"],
        db_user=config["db_user"],
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=active_sessions,
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
