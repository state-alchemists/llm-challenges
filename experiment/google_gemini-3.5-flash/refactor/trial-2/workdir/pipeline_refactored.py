"""
Pipeline Refactored Script.

Extracts server log entries using regular expressions, transforms the parsed
data to calculate metrics (such as active sessions, error counts, and API
latencies), and loads these metrics into both a SQLite database and an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional


# Configuration from Environment Variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")
REPORT_PATH = os.getenv("REPORT_PATH", "report.html")

# Regular Expression Patterns for Parsing Logs
# Match standard log structure: "YYYY-MM-DD HH:MM:SS LEVEL MESSAGE"
LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(INFO|ERROR|WARN)\s+(.*)$"
)
# Match user-related message: "User <uid> <action>"
USER_ACTION_RE = re.compile(r"^User\s+(\S+)\s+(.+)$")
# Match API-related message: "API <endpoint> took <latency_ms>ms"
API_METRIC_RE = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass
class LogRecord:
    """Represents a single parsed log record."""
    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass
class PipelineMetrics:
    """Represents aggregated metrics derived from transformed log data."""
    error_counts: Dict[str, int]
    api_averages: Dict[str, float]
    active_session_count: int


def extract_logs(log_file_path: str) -> List[LogRecord]:
    """
    Reads a log file, parses each line using regular expressions,
    and extracts structured LogRecord objects.
    """
    records: List[LogRecord] = []
    if not os.path.exists(log_file_path):
        return records

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp, level, message = match.groups()
            record = LogRecord(timestamp=timestamp, level=level, message=message)

            if level == "INFO":
                user_match = USER_ACTION_RE.match(message)
                if user_match:
                    record.user_id = user_match.group(1)
                    record.action = user_match.group(2)
                else:
                    api_match = API_METRIC_RE.match(message)
                    if api_match:
                        record.endpoint = api_match.group(1)
                        latency_str = api_match.group(2)
                        record.latency_ms = int(latency_str) if latency_str else 0

            records.append(record)

    return records


def transform_logs(records: List[LogRecord]) -> PipelineMetrics:
    """
    Transforms raw log records to aggregate error counts, API latencies, and
    computes active user sessions.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for record in records:
        if record.level == "ERROR":
            error_counts[record.message] = error_counts.get(record.message, 0) + 1

        elif record.level == "INFO":
            if record.user_id is not None and record.action is not None:
                if "logged in" in record.action:
                    sessions[record.user_id] = record.timestamp
                elif "logged out" in record.action and record.user_id in sessions:
                    sessions.pop(record.user_id)

            elif record.endpoint is not None and record.latency_ms is not None:
                api_latencies.setdefault(record.endpoint, []).append(record.latency_ms)

    api_averages: Dict[str, float] = {}
    for ep, latencies in api_latencies.items():
        if latencies:
            api_averages[ep] = sum(latencies) / len(latencies)
        else:
            api_averages[ep] = 0.0

    return PipelineMetrics(
        error_counts=error_counts,
        api_averages=api_averages,
        active_session_count=len(sessions),
    )


def load_to_database(db_path: str, metrics: PipelineMetrics) -> None:
    """
    Inserts transformed metrics into the database using parameterized queries.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in metrics.error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, avg in metrics.api_averages.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(report_path: str, metrics: PipelineMetrics) -> None:
    """
    Generates an HTML report containing error summaries, API latencies, and
    active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Executes the extraction, transformation, and load steps of the log pipeline."""
    # Ensure log file exists for demonstration if not already present
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    records = extract_logs(LOG_FILE)

    # Transform
    metrics = transform_logs(records)

    # Load
    load_to_database(DB_PATH, metrics)
    generate_html_report(REPORT_PATH, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
