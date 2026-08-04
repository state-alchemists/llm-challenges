"""
Server log processing pipeline.

Reads server logs, extracts metrics, persists them to a SQLite database,
and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class ErrorRecord:
    """Represents an ERROR log entry."""

    dt: str
    message: str


@dataclass
class WarnRecord:
    """Represents a WARN log entry."""

    dt: str
    message: str


@dataclass
class UserRecord:
    """Represents a user session log entry."""

    dt: str
    user_id: str
    action: str


@dataclass
class ApiRecord:
    """Represents an API call log entry."""

    dt: str
    endpoint: str
    ms: int


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config object populated from environment variables.

    Raises:
        ValueError: If DB_PORT is not a valid integer.
    """
    port_str = os.getenv("DB_PORT", "5432")
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(f"DB_PORT must be an integer, got: {port_str}") from exc

    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=port,
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# Regex patterns for log line parsing
_LOG_LINE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<level>\w+) (?P<rest>.*)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")


def extract_logs(
    log_file: str,
) -> Tuple[List[ErrorRecord], List[WarnRecord], List[UserRecord], List[ApiRecord]]:
    """Extract and parse log records from the given file.

    Args:
        log_file: Path to the server log file.

    Returns:
        A tuple of (errors, warnings, user_records, api_records).
    """
    errors: List[ErrorRecord] = []
    warnings: List[WarnRecord] = []
    user_records: List[UserRecord] = []
    api_records: List[ApiRecord] = []

    if not os.path.exists(log_file):
        return errors, warnings, user_records, api_records

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            dt = match.group("dt")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                errors.append(ErrorRecord(dt=dt, message=rest))
            elif level == "WARN":
                warnings.append(WarnRecord(dt=dt, message=rest))
            elif level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    user_records.append(
                        UserRecord(
                            dt=dt,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    ms_str = api_match.group("ms")
                    api_records.append(
                        ApiRecord(
                            dt=dt,
                            endpoint=api_match.group("endpoint"),
                            ms=int(ms_str) if ms_str is not None else 0,
                        )
                    )

    return errors, warnings, user_records, api_records


def transform_data(
    errors: List[ErrorRecord],
    user_records: List[UserRecord],
    api_records: List[ApiRecord],
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Transform extracted records into aggregates.

    Args:
        errors: List of error records.
        user_records: List of user session records.
        api_records: List of API call records.

    Returns:
        A tuple of (error_summary, api_latencies, active_sessions).
    """
    error_summary: Dict[str, int] = {}
    for rec in errors:
        error_summary[rec.message] = error_summary.get(rec.message, 0) + 1

    api_latencies: Dict[str, List[int]] = {}
    for rec in api_records:
        api_latencies.setdefault(rec.endpoint, []).append(rec.ms)

    sessions: Dict[str, str] = {}
    for rec in user_records:
        if "logged in" in rec.action:
            sessions[rec.user_id] = rec.dt
        elif "logged out" in rec.action and rec.user_id in sessions:
            sessions.pop(rec.user_id)

    active_sessions = len(sessions)

    return error_summary, api_latencies, active_sessions


def load_data(
    config: Config,
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Load transformed aggregates into the SQLite database.

    Uses parameterized queries to prevent SQL injection.

    Args:
        config: Application configuration.
        error_summary: Mapping of error message to occurrence count.
        api_latencies: Mapping of endpoint to list of response times in ms.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        for msg, count in error_summary.items():
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
    finally:
        conn.close()


def generate_report(
    error_summary: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Generate the HTML report.

    Args:
        error_summary: Mapping of error message to occurrence count.
        api_latencies: Mapping of endpoint to list of response times in ms.
        active_sessions: Number of currently active sessions.
        output_path: Path where the report will be written.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
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

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def create_sample_log_file(log_file: str) -> None:
    """Create a sample log file if one does not already exist."""
    if os.path.exists(log_file):
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]

    with open(log_file, "w", encoding="utf-8") as f:
        for line in sample_lines:
            f.write(line + "\n")


def main() -> None:
    """Run the ETL pipeline."""
    config = load_config()
    create_sample_log_file(config.log_file)

    errors, _warnings, user_records, api_records = extract_logs(config.log_file)
    error_summary, api_latencies, active_sessions = transform_data(
        errors, user_records, api_records
    )
    load_data(config, error_summary, api_latencies)
    generate_report(error_summary, api_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
