"""Pipeline refactored script.

Processes server logs, extracts metrics, stores them in SQLite database,
and generates an HTML report.
"""

from dataclasses import dataclass
import datetime
import os
from pathlib import Path
import re
import sqlite3
from typing import Any


@dataclass(frozen=True, slots=True)
class Config:
    """Configuration loaded from environment variables."""

    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a single log line using regex.

    Returns a dictionary of parsed fields or None if unmatched.
    """
    pattern = re.compile(
        r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>[A-Z]+)\s+(?P<msg>.*)$"
    )
    match = pattern.match(line)
    if not match:
        return None
    return match.groupdict()


def extract_logs(log_file: str) -> list[dict[str, Any]]:
    """Extract and parse all log lines from the specified log file.

    Returns a list of parsed events.
    """
    events: list[dict[str, Any]] = []
    log_path = Path(log_file)
    if not log_path.exists():
        return events

    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_log_line(line)
            if parsed:
                events.append(parsed)
    return events


def transform(
    events: list[dict[str, Any]]
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """Transform raw log events into structured metrics.

    Returns a tuple of (error_counts, api_metrics, active_sessions_count).
    """
    error_counts: dict[str, int] = {}
    api_metrics: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for ev in events:
        level, msg, dt = ev["level"], ev["msg"], ev["dt"]
        if level == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif level == "INFO" and msg.startswith("User"):
            user_match = re.match(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$", msg)
            if user_match:
                uid, action = user_match.group("uid"), user_match.group("action")
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
        elif level == "INFO" and msg.startswith("API"):
            api_match = re.match(
                r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?", msg
            )
            if api_match:
                endpoint = api_match.group("endpoint")
                dur = int(api_match.group("dur") or "0")
                api_metrics.setdefault(endpoint, []).append(dur)

    return error_counts, api_metrics, len(sessions)


def load_db(
    config: Config,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
) -> None:
    """Connect to SQLite and load metrics using parameterized queries."""
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    with sqlite3.connect(config.db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())
        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, times in api_metrics.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, ep, avg),
            )
        conn.commit()


def load_html(
    report_path: str,
    error_counts: dict[str, int],
    api_metrics: dict[str, list[int]],
    active_sessions_count: int,
) -> None:
    """Generate the HTML report output matching the exact format."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Orchestrate the ETL pipeline."""
    config = Config()

    # Extract
    events = extract_logs(config.log_file)

    # Transform
    error_counts, api_metrics, active_sessions_count = transform(events)

    # Load
    load_db(config, error_counts, api_metrics)
    load_html("report.html", error_counts, api_metrics, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    default_log_file = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(default_log_file):
        with open(default_log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
