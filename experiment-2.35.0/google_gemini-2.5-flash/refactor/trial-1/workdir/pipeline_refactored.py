import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

@dataclass(frozen=True, slots=True)
class Config:
    """Configuration for the log processing pipeline."""
    db_path: Path
    log_file_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Represents a single parsed log entry."""
    timestamp: str
    level: str
    message: str


def configure() -> Config:
    """
    Loads configuration from environment variables.

    Returns:
        Config: An object containing all configuration settings.
    """
    db_path = Path(os.getenv("DB_PATH", "metrics.db"))
    log_file_path = Path(os.getenv("LOG_FILE", "server.log"))
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "admin")
    db_pass = os.getenv("DB_PASS", "password123")
    return Config(db_path, log_file_path, db_host, db_port, db_user, db_pass)


def extract_logs(log_file_path: Path) -> Iterator[LogEntry]:
    """
    Reads and parses log entries from the specified log file using regex.

    Args:
        log_file_path (Path): The path to the server log file.

    Yields:
        LogEntry: A parsed log entry.
    """
    log_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"(?P<level>\w+) (?P<message>.*)$"
    )
    if not log_file_path.exists():
        print(f"Log file not found: {log_file_path}")
        return

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if match:
                yield LogEntry(**match.groupdict())


def transform_data(
    parsed_logs: Iterator[LogEntry],
) -> tuple[dict[str, int], defaultdict[str, list[int]], dict[str, str]]:
    """
    Transforms raw log data into structured summaries for errors, API latency, and active sessions.

    Args:
        parsed_logs (Iterator[LogEntry]): An iterator of parsed log entries.

    Returns:
        tuple[dict[str, int], defaultdict[str, list[int]], dict[str, str]]:
            A tuple containing:
            - error_summary: A dictionary mapping error messages to their counts.
            - api_latency: A dictionary mapping API endpoints to a list of latencies (ms).
            - active_sessions: A dictionary mapping user IDs to their login timestamps.
    """
    error_summary: dict[str, int] = defaultdict(int)
    api_latency: defaultdict[str, list[int]] = defaultdict(list)
    active_sessions: dict[str, str] = {}

    user_login_pattern = re.compile(r"User (?P<user_id>\w+) logged in")
    user_logout_pattern = re.compile(r"User (?P<user_id>\w+) logged out")
    api_call_pattern = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")

    for entry in parsed_logs:
        if entry.level == "ERROR":
            error_summary[entry.message.strip()] += 1
        elif entry.level == "INFO":
            user_login_match = user_login_pattern.search(entry.message)
            user_logout_match = user_logout_pattern.search(entry.message)
            api_call_match = api_call_pattern.search(entry.message)

            if user_login_match:
                user_id = user_login_match.group("user_id")
                active_sessions[user_id] = entry.timestamp
            elif user_logout_match:
                user_id = user_logout_match.group("user_id")
                active_sessions.pop(user_id, None)
            elif api_call_match:
                endpoint = api_call_match.group("endpoint")
                duration = int(api_call_match.group("duration"))
                api_latency[endpoint].append(duration)
        elif entry.level == "WARN":
            # Currently, warnings are just parsed but not specifically transformed for the report
            pass
    return error_summary, api_latency, active_sessions


def load_data_to_db(
    config: Config,
    error_summary: dict[str, int],
    api_latency: defaultdict[str, list[int]],
) -> None:
    """
    Connects to the database and loads the processed error and API metric data.

    Args:
        config (Config): Configuration object containing DB connection details.
        error_summary (dict[str, int]): A dictionary mapping error messages to their counts.
        api_latency (defaultdict[str, list[int]]): A dictionary mapping API endpoints to a list of latencies (ms).
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    conn = sqlite3.connect(config.db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: dict[str, int],
    api_latency: defaultdict[str, list[int]],
    active_sessions: dict[str, str],
    report_file: Path = Path("report.html"),
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary (dict[str, int]): A dictionary mapping error messages to their counts.
        api_latency (defaultdict[str, list[int]]): A dictionary mapping API endpoints to a list of latencies (ms).
        active_sessions (dict[str, str]): A dictionary mapping user IDs to their login timestamps.
        report_file (Path): The path to the output HTML report file.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></td>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_file, "w") as f:
        f.write(out)


def main() -> None:
    """Orchestrates the log processing and report generation pipeline."""
    config = configure()

    if not config.log_file_path.exists():
        print(f"Creating dummy log file at {config.log_file_path}")
        with open(config.log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    parsed_logs = extract_logs(config.log_file_path)
    error_summary, api_latency, active_sessions = transform_data(parsed_logs)
    load_data_to_db(config, error_summary, api_latency)
    generate_report(error_summary, api_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
