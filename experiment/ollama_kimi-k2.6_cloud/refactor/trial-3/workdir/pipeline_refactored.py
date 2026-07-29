"""Server log ETL pipeline: extract, transform, load, and report."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class ErrorEntry:
    """A parsed ERROR log line."""

    timestamp: str
    message: str


@dataclass
class WarnEntry:
    """A parsed WARN log line."""

    timestamp: str
    message: str


@dataclass
class UserEntry:
    """A parsed User-session INFO log line."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiEntry:
    """A parsed API-latency INFO log line."""

    timestamp: str
    endpoint: str
    duration_ms: int


# Base log pattern: "YYYY-MM-DD HH:MM:SS LEVEL message..."
_BASE_LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|WARN|ERROR) "
    r"(?P<message>.*)$"
)

# INFO sub-patterns
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


def load_config() -> Dict[str, str]:
    """Load runtime configuration from environment variables.

    Returns:
        A dictionary of configuration values. Paths fall back to the
        original defaults so the script remains runnable out of the box.
    """
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": os.environ.get("DB_PORT", "5432"),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


def extract_log_entries(
    log_path: str,
) -> Tuple[List[ErrorEntry], List[WarnEntry], List[UserEntry], List[ApiEntry]]:
    """Parse server log lines into structured dataclasses using regex.

    Args:
        log_path: Path to the server log file.

    Returns:
        Four lists: errors, warnings, user entries, and API entries.
    """
    errors: List[ErrorEntry] = []
    warnings: List[WarnEntry] = []
    users: List[UserEntry] = []
    apis: List[ApiEntry] = []

    if not os.path.exists(log_path):
        return errors, warnings, users, apis

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            base_match = _BASE_LOG_RE.match(line)
            if not base_match:
                continue

            timestamp = base_match.group("timestamp")
            level = base_match.group("level")
            message = base_match.group("message")

            if level == "ERROR":
                errors.append(ErrorEntry(timestamp=timestamp, message=message))
            elif level == "WARN":
                warnings.append(WarnEntry(timestamp=timestamp, message=message))
            elif level == "INFO":
                user_match = _USER_RE.match(message)
                if user_match:
                    users.append(
                        UserEntry(
                            timestamp=timestamp,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(message)
                if api_match:
                    apis.append(
                        ApiEntry(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            duration_ms=int(api_match.group("duration")),
                        )
                    )
                    continue
            # Unmatched INFO lines are silently ignored to match legacy behaviour.

    return errors, warnings, users, apis


def transform_data(
    errors: List[ErrorEntry],
    warnings: List[WarnEntry],
    users: List[UserEntry],
    apis: List[ApiEntry],
) -> Tuple[Dict[str, int], Dict[str, float], int]:
    """Aggregate extracted log data into report-ready metrics.

    Args:
        errors: Parsed ERROR entries.
        warnings: Parsed WARN entries (kept for extensibility).
        users: Parsed User-session entries.
        apis: Parsed API-latency entries.

    Returns:
        A tuple of (error_counts, api_avg_latency, active_session_count).
    """
    error_counts: Dict[str, int] = {}
    for entry in errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for entry in apis:
        endpoint_stats.setdefault(entry.endpoint, []).append(entry.duration_ms)

    api_avg_latency: Dict[str, float] = {}
    for endpoint, times in endpoint_stats.items():
        api_avg_latency[endpoint] = sum(times) / len(times)

    sessions: Dict[str, str] = {}
    for entry in users:
        if "logged in" in entry.action:
            sessions[entry.user_id] = entry.timestamp
        elif "logged out" in entry.action and entry.user_id in sessions:
            sessions.pop(entry.user_id)

    active_sessions = len(sessions)
    return error_counts, api_avg_latency, active_sessions


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_avg_latency: Dict[str, float],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message -> occurrence count.
        api_avg_latency: Mapping of endpoint -> average latency in ms.
    """
    conn = sqlite3.connect(db_path)
    try:
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

        for endpoint, avg in api_avg_latency.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_avg_latency: Dict[str, float],
    active_sessions: int,
    output_path: str,
) -> None:
    """Render an HTML report with error summary, API latency, and active sessions.

    Args:
        error_counts: Mapping of error message -> occurrence count.
        api_avg_latency: Mapping of endpoint -> average latency in ms.
        active_sessions: Number of currently logged-in users.
        output_path: File path to write the HTML report to.
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

    for ep, avg in api_avg_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{active_sessions} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = load_config()

    log_file = config["log_file"]
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    errors, warnings, users, apis = extract_log_entries(log_file)
    error_counts, api_avg_latency, active_sessions = transform_data(
        errors, warnings, users, apis
    )
    load_to_database(config["db_path"], error_counts, api_avg_latency)
    generate_report(error_counts, api_avg_latency, active_sessions, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
