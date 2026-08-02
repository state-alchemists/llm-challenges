import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Configuration loaded from environment variables with sensible defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Precompiled regular expressions for robust parsing
LOG_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN|DEBUG) (.*)$"
)
USER_PATTERN: re.Pattern[str] = re.compile(r"^User (\S+) (.+)$")
API_PATTERN: re.Pattern[str] = re.compile(r"^API (\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Represents a structured log entry."""

    timestamp: str
    level: str
    payload: str


@dataclass(frozen=True, slots=True)
class PipelineReportData:
    """Represents the aggregated metrics and active session count for reporting."""

    error_counts: dict[str, int]
    api_averages: dict[str, float]
    active_sessions_count: int


def extract(log_path: Path) -> list[LogRecord]:
    """Reads the log file and extracts structured LogRecord instances."""
    records: list[LogRecord] = []
    if not log_path.exists():
        return records

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            match = LOG_LINE_PATTERN.match(stripped_line)
            if match:
                timestamp, level, payload = match.groups()
                records.append(
                    LogRecord(
                        timestamp=timestamp, level=level, payload=payload
                    )
                )
    return records


def _process_error_record(
    record: LogRecord, error_counts: dict[str, int]
) -> None:
    """Processes an error record and updates error counts."""
    error_msg = record.payload.strip()
    error_counts[error_msg] = error_counts.get(error_msg, 0) + 1


def _process_info_record(
    record: LogRecord,
    sessions: dict[str, str],
    api_calls: dict[str, list[int]],
) -> None:
    """Processes an info record to update sessions and api metrics."""
    # Check for User session actions
    user_match = USER_PATTERN.match(record.payload)
    if user_match:
        user_id = user_match.group(1)
        action = user_match.group(2).strip()
        if "logged in" in action:
            sessions[user_id] = record.timestamp
        elif "logged out" in action and user_id in sessions:
            sessions.pop(user_id)

    # Check for API call duration metrics
    api_match = API_PATTERN.match(record.payload)
    if api_match:
        endpoint = api_match.group(1)
        duration_str = api_match.group(2)
        duration_ms = int(duration_str) if duration_str is not None else 0
        api_calls.setdefault(endpoint, []).append(duration_ms)


def transform(records: list[LogRecord]) -> PipelineReportData:
    """Transforms raw log records into aggregated metrics and session counts."""
    error_counts: dict[str, int] = {}
    api_calls: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}  # user_id -> timestamp

    for record in records:
        if record.level == "ERROR":
            _process_error_record(record, error_counts)
        elif record.level == "INFO":
            _process_info_record(record, sessions, api_calls)

    api_averages: dict[str, float] = {
        endpoint: sum(times) / len(times)
        for endpoint, times in api_calls.items()
    }

    return PipelineReportData(
        error_counts=error_counts,
        api_averages=api_averages,
        active_sessions_count=len(sessions),
    )


def load_to_database(db_path: Path, data: PipelineReportData) -> None:
    """Inserts aggregated metrics into the SQLite database."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    now_str = str(datetime.datetime.now())

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        # Parameterized inserts to prevent SQL injection
        for msg, count in data.error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for endpoint, avg_ms in data.api_averages.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, endpoint, avg_ms),
            )
        conn.commit()


def load_to_html(report_path: Path, data: PipelineReportData) -> None:
    """Generates an HTML report from the pipeline metrics."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in data.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in data.api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{data.active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Main pipeline entry point that coordinates the ETL workflow."""
    log_path = Path(LOG_FILE)
    db_path = Path(DB_PATH)
    report_path = Path("report.html")

    records = extract(log_path)
    transformed_data = transform(records)

    load_to_database(db_path, transformed_data)
    load_to_html(report_path, transformed_data)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
