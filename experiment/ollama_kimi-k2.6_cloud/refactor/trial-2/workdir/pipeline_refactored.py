"""Server log processing pipeline.

Reads server logs, extracts metrics and errors, persists aggregates to SQLite,
and produces an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = "metrics.db"
DEFAULT_LOG_FILE = "server.log"
DEFAULT_REPORT_FILE = "report.html"

LOG_LEVEL_PATTERN = re.compile(r"^(INFO|ERROR|WARN)$")
# Full log line: <ISO-like datetime> <LEVEL> <message>
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
)
# INFO sub-patterns
USER_ACTION_PATTERN = re.compile(r"^User (\S+) (.+)$")
API_CALL_PATTERN = re.compile(r"^API (\S+) took (\d+)ms$")


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: Path
    log_file: Path
    report_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Load configuration from environment variables.

    Falls back to sensible defaults so the script can run out-of-the-box
    for demonstration purposes.
    """
    return Config(
        db_path=Path(os.getenv("PIPELINE_DB_PATH", DEFAULT_DB_PATH)),
        log_file=Path(os.getenv("PIPELINE_LOG_FILE", DEFAULT_LOG_FILE)),
        report_file=Path(os.getenv("PIPELINE_REPORT_FILE", DEFAULT_REPORT_FILE)),
        db_host=os.getenv("PIPELINE_DB_HOST", "localhost"),
        db_port=int(os.getenv("PIPELINE_DB_PORT", "5432")),
        db_user=os.getenv("PIPELINE_DB_USER", "admin"),
        db_pass=os.getenv("PIPELINE_DB_PASS", ""),
    )


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """An INFO-level user-centric event extracted from a log entry."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An INFO-level API latency event extracted from a log entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class TransformedData:
    """The aggregate data produced by the Transform step."""

    errors: dict[str, int] = field(default_factory=dict)
    api_latency: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)
    warnings: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_logs(log_path: Path) -> list[LogEntry]:
    """Read and parse log lines from *log_path*.

    Returns a list of :class:`LogEntry` objects for every line that matches
    the expected format.  Malformed lines are silently skipped.
    """
    entries: list[LogEntry] = []
    if not log_path.exists():
        return entries

    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            match = LOG_LINE_PATTERN.match(line)
            if not match:
                continue
            timestamp, level, message = match.groups()
            entries.append(LogEntry(timestamp=timestamp, level=level, message=message))

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_data(entries: list[LogEntry]) -> TransformedData:
    """Aggregate parsed log entries into report-ready structures.

    Counts error occurrences, collects API latencies per endpoint, and
    tracks active sessions based on login / logout events.
    """
    data = TransformedData()

    for entry in entries:
        if entry.level == "ERROR":
            data.errors[entry.message] = data.errors.get(entry.message, 0) + 1

        elif entry.level == "WARN":
            data.warnings.append({"timestamp": entry.timestamp, "message": entry.message})

        elif entry.level == "INFO":
            user_match = USER_ACTION_PATTERN.match(entry.message)
            if user_match:
                user_id, action = user_match.groups()
                if "logged in" in action:
                    data.active_sessions[user_id] = entry.timestamp
                elif "logged out" in action and user_id in data.active_sessions:
                    data.active_sessions.pop(user_id, None)
                continue

            api_match = API_CALL_PATTERN.match(entry.message)
            if api_match:
                endpoint, duration_str = api_match.groups()
                data.api_latency.setdefault(endpoint, []).append(int(duration_str))

    return data


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def init_db_schema(conn: sqlite3.Connection) -> None:
    """Create required tables if they do not already exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def persist_metrics(
    conn: sqlite3.Connection, data: TransformedData, run_dt: datetime.datetime
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries."""
    run_dt_iso = run_dt.isoformat()

    for msg, count in data.errors.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (run_dt_iso, msg, count),
        )

    for endpoint, times in data.api_latency.items():
        avg_ms = sum(times) / len(times)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (run_dt_iso, endpoint, avg_ms),
        )


def load_to_db(data: TransformedData, db_path: Path) -> None:
    """Open the SQLite database, initialise the schema, and write metrics."""
    with sqlite3.connect(db_path) as conn:
        init_db_schema(conn)
        persist_metrics(conn, data, datetime.datetime.now())
        conn.commit()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_html(data: TransformedData, output_path: Path) -> None:
    """Write an HTML report summarising errors, API latency, and active sessions."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.errors.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, times in data.api_latency.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(data.active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_sample_log(path: Path) -> None:
    """Create a sample log file for demonstration when no real log exists."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")


def main() -> None:
    """Run the full ETL pipeline."""
    config = load_config()

    if not config.log_file.exists():
        generate_sample_log(config.log_file)

    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )

    entries = extract_logs(config.log_file)
    data = transform_data(entries)
    load_to_db(data, config.db_path)
    generate_html(data, config.report_file)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
