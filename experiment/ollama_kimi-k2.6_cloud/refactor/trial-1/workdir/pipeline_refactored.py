"""ETL pipeline that parses server logs and generates an HTML report.

Pipeline stages:
    1. Extract   – read the log file and parse lines with regex.
    2. Transform – aggregate errors, API latencies, and active user sessions.
    3. Load      – persist aggregates to SQLite using parameterized queries.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, NamedTuple, Tuple


class Config(NamedTuple):
    """Runtime configuration sourced from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


class LogEntry(NamedTuple):
    """A single parsed log line."""
    timestamp: str
    level: str
    message: str


# Regex patterns for log parsing.
_LOG_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<message>.*)$"
)

_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$")


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        A Config object populated from the environment, using sensible defaults
        when a variable is not set.
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


def _seed_sample_log(path: str) -> None:
    """Create a sample log file when the real file is missing."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(path, "w") as f:
        f.writelines(lines)


def extract(log_path: str) -> List[LogEntry]:
    """Read the server log and parse each line into a structured entry.

    Args:
        log_path: Path to the log file on disk.

    Returns:
        A list of parsed log entries.
    """
    entries: List[LogEntry] = []
    if not os.path.exists(log_path):
        return entries

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue
            timestamp = f"{match.group('date')} {match.group('time')}"
            entries.append(
                LogEntry(
                    timestamp=timestamp,
                    level=match.group("level"),
                    message=match.group("message"),
                )
            )
    return entries


def transform(
    entries: List[LogEntry],
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Aggregate raw log entries into the metrics required by the report.

    Args:
        entries: Parsed log entries from the Extract stage.

    Returns:
        A three-tuple of:
        - error_counts: mapping of error message → occurrence count.
        - api_latencies: mapping of endpoint → list of response times in ms.
        - active_sessions: mapping of user id → most recent login timestamp.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = defaultdict(list)
    active_sessions: Dict[str, str] = {}

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
            continue

        if entry.level == "WARN":
            # Parsed for completeness but not surfaced in the current report.
            continue

        if entry.level == "INFO":
            user_match = _USER_RE.match(entry.message)
            if user_match:
                uid = user_match.group("uid")
                action = user_match.group("action").strip()
                if "logged in" in action:
                    active_sessions[uid] = entry.timestamp
                elif "logged out" in action and uid in active_sessions:
                    active_sessions.pop(uid)
                continue

            api_match = _API_RE.match(entry.message)
            if api_match:
                endpoint = api_match.group("endpoint")
                duration_str = api_match.group("duration")
                duration = int(duration_str) if duration_str is not None else 0
                api_latencies[endpoint].append(duration)

    return error_counts, dict(api_latencies), active_sessions


def load(
    config: Config,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        config: Database connection configuration.
        error_counts: Mapping of error message → occurrence count.
        api_latencies: Mapping of endpoint → list of response times in ms.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
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

    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_session_count: int,
) -> str:
    """Build the HTML report string.

    Args:
        error_counts: Mapping of error message → occurrence count.
        api_averages: Mapping of endpoint → average latency in ms.
        active_session_count: Number of currently active user sessions.

    Returns:
        Complete HTML document as a string.
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

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for ep, avg in api_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """Execute the full ETL pipeline."""
    config = load_config()

    if not os.path.exists(config.log_file):
        _seed_sample_log(config.log_file)

    entries = extract(config.log_file)
    error_counts, api_latencies, active_sessions = transform(entries)
    api_averages = {ep: sum(times) / len(times) for ep, times in api_latencies.items()}

    load(config, error_counts, api_latencies)

    report_html = generate_report(error_counts, api_averages, len(active_sessions))
    with open("report.html", "w") as f:
        f.write(report_html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
