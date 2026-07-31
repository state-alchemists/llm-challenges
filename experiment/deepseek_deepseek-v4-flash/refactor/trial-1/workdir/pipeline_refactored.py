#!/usr/bin/env python3
"""Server log reporting pipeline, refactored into an Extract - Transform - Load structure.

Reads a server log file, parses each line with regular expressions, aggregates
error counts / API latency statistics / active session state, persists the
aggregates to SQLite using parameterized queries, and writes ``report.html``
containing the same information as the original script.

All configuration comes from environment variables:

- ``LOG_FILE``  — path to the input server log (default: ``server.log``)
- ``DB_PATH``   — path to the SQLite database (default: ``metrics.db``)
- ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASS`` — database connection
  metadata (informational; SQLite does not use them)

Usage::

    LOG_FILE=server.log DB_PATH=metrics.db python pipeline_refactored.py
"""

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# One line per log record: "<timestamp> <LEVEL> <message>"
LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<message>.*)$"
)
# INFO line for session changes: "User <id> <action>"
USER_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.*)$")
# INFO line for API calls: "API <endpoint> took <ms>ms"
API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$")

REPORT_FILE = "report.html"

SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@dataclass(frozen=True)
class Config:
    """Pipeline configuration resolved from environment variables."""

    log_file: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class ReportData:
    """Aggregated metrics ready for loading and reporting."""

    error_counts: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int


def load_config() -> Config:
    """Read all pipeline configuration from environment variables.

    Falls back to defaults matching the original hardcoded values so the
    script remains runnable out of the box.
    """
    return Config(
        log_file=Path(os.getenv("LOG_FILE", "server.log")),
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single log line into a structured event.

    Returns ``None`` for lines that do not match any known format.
    Recognized events: error, warn, user session, and API latency.
    """
    match = LINE_RE.match(line)
    if not match:
        return None
    timestamp: str = match.group("timestamp")
    level: str = match.group("level")
    message: str = match.group("message")

    if level == "ERROR":
        return {"timestamp": timestamp, "type": "error", "message": message}
    if level == "WARN":
        return {"timestamp": timestamp, "type": "warn", "message": message}
    if level == "INFO":
        user_match = USER_RE.match(message)
        if user_match:
            return {
                "timestamp": timestamp,
                "type": "user",
                "uid": user_match.group("uid"),
                "action": user_match.group("action"),
            }
        api_match = API_RE.match(message)
        if api_match:
            return {
                "timestamp": timestamp,
                "type": "api",
                "endpoint": api_match.group("endpoint"),
                "latency_ms": int(api_match.group("ms") or 0),
            }
    return None


def extract_events(log_path: Path) -> List[Dict[str, Any]]:
    """Extract: read the log file and parse every line into an event list."""
    events: List[Dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            event = parse_log_line(line.rstrip("\n"))
            if event is not None:
                events.append(event)
    return events


def transform_events(events: List[Dict[str, Any]]) -> ReportData:
    """Transform: aggregate parsed events into error counts, latency stats, sessions.

    Tracks active sessions by replaying login/logout events in order, so the
    count reflects the state at the end of the log.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for event in events:
        event_type = event["type"]
        if event_type == "error":
            message = event["message"]
            error_counts[message] = error_counts.get(message, 0) + 1
        elif event_type == "api":
            endpoint = event["endpoint"]
            api_latencies.setdefault(endpoint, []).append(event["latency_ms"])
        elif event_type == "user":
            uid = event["uid"]
            action = event["action"]
            if "logged in" in action:
                sessions[uid] = event["timestamp"]
            elif "logged out" in action and uid in sessions:
                del sessions[uid]

    return ReportData(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=len(sessions),
    )


def load_metrics(
    db_path: Path,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Load: persist aggregated metrics to SQLite with parameterized queries.

    Uses ``?`` placeholders for every value — no string interpolation is
    applied to SQL statements, which prevents injection via log content.
    """
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        for message, count in error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, message, count),
            )
        for endpoint, latencies in api_latencies.items():
            avg_ms = sum(latencies) / len(latencies)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg_ms),
            )


def generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: int,
) -> str:
    """Build the HTML report: error summary, API latency table, session count.

    Message and endpoint text is HTML-escaped before embedding.
    """
    parts = ["<html>\n<head><title>System Report</title></head>\n<body>\n"]
    parts.append("<h1>Error Summary</h1>\n<ul>\n")
    for err_msg, count in error_counts.items():
        parts.append(
            f"<li><b>{html.escape(err_msg)}</b>: {count} occurrences</li>\n"
        )
    parts.append("</ul>\n")

    parts.append("<h2>API Latency</h2>\n<table border='1'>\n")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n")
    for endpoint, latencies in api_latencies.items():
        avg_ms = sum(latencies) / len(latencies)
        parts.append(
            f"<tr><td>{html.escape(endpoint)}</td>"
            f"<td>{round(avg_ms, 1)}</td></tr>\n"
        )
    parts.append("</table>\n")

    parts.append("<h2>Active Sessions</h2>\n")
    parts.append(f"<p>{active_sessions} user(s) currently active</p>\n")
    parts.append("</body>\n</html>")
    return "".join(parts)


def write_report(report_path: Path, content: str) -> None:
    """Write the rendered HTML report to disk."""
    report_path.write_text(content, encoding="utf-8")


def write_sample_log(log_path: Path) -> None:
    """Create a small sample log so the pipeline is runnable out of the box."""
    log_path.write_text(SAMPLE_LOG, encoding="utf-8")


def main() -> None:
    """Run the full extract - transform - load pipeline and write the report."""
    config = load_config()
    if not config.log_file.exists():
        write_sample_log(config.log_file)

    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )

    events = extract_events(config.log_file)
    report_data = transform_events(events)
    load_metrics(
        config.db_path,
        report_data.error_counts,
        report_data.api_latencies,
    )

    report_html = generate_report(
        report_data.error_counts,
        report_data.api_latencies,
        report_data.active_sessions,
    )
    write_report(Path(REPORT_FILE), report_html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
