"""Server log pipeline: extract, transform, load, and report.

Reads a structured server log, aggregates error and API-latency metrics,
tracks active user sessions, persists the results to SQLite, and writes an
HTML summary report.  All configuration is sourced from environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration (loaded from environment)
# ---------------------------------------------------------------------------

DEFAULT_LOG_FILE = "server.log"
DEFAULT_DB_PATH = "metrics.db"


@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a ``Config`` instance from the process environment."""
        return cls(
            db_path=os.getenv("DB_PATH", DEFAULT_DB_PATH),
            log_file=os.getenv("LOG_FILE", DEFAULT_LOG_FILE),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
        )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ParsedLogEntry:
    """A single log line after parsing."""

    timestamp: str
    level: str
    message: str


@dataclass
class TransformedData:
    """Aggregated data ready for loading and reporting."""

    error_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    api_latencies: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    active_sessions: dict[str, str] = field(default_factory=dict)
    warn_entries: list[ParsedLogEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# General log-line pattern: TIMESTAMP LEVEL MESSAGE...
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)

# Pattern for user session lines: User <id> <action>
_USER_RE = re.compile(
    r"User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

# Pattern for API latency lines: API <endpoint> took <duration>ms
_API_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$"
)


def extract_logs(log_file: str) -> list[ParsedLogEntry]:
    """Parse *log_file* into a list of ``ParsedLogEntry`` objects.

    Missing or unreadable files are handled gracefully by returning an empty
    list and printing a warning.
    """
    entries: list[ParsedLogEntry] = []
    path = Path(log_file)

    if not path.exists():
        print(f"Warning: log file '{log_file}' not found. No data extracted.")
        return entries

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue
            entries.append(
                ParsedLogEntry(
                    timestamp=match.group("timestamp"),
                    level=match.group("level"),
                    message=match.group("message"),
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_data(entries: list[ParsedLogEntry]) -> TransformedData:
    """Aggregate *entries* into error counts, API latencies, and session state."""
    data = TransformedData()

    for entry in entries:
        if entry.level == "ERROR":
            data.error_counts[entry.message] += 1
        elif entry.level == "WARN":
            data.warn_entries.append(entry)
        elif entry.level == "INFO":
            if entry.message.startswith("User "):
                user_match = _USER_RE.match(entry.message)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action")
                    if "logged in" in action:
                        data.active_sessions[uid] = entry.timestamp
                    elif "logged out" in action and uid in data.active_sessions:
                        data.active_sessions.pop(uid)
            elif entry.message.startswith("API "):
                api_match = _API_RE.match(entry.message)
                if api_match:
                    endpoint = api_match.group("endpoint")
                    duration = int(api_match.group("duration"))
                    data.api_latencies[endpoint].append(duration)

    return data


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(data: TransformedData, db_path: str) -> None:
    """Persist aggregated *data* into the SQLite database at *db_path*.

    Uses parameterized queries to eliminate SQL-injection risk.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    for msg, count in data.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in data.api_latencies.items():
        avg_ms = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(data: TransformedData, output_path: str = "report.html") -> None:
    """Write an HTML summary of *data* to *output_path*."""
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # Error Summary
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in data.error_counts.items():
        lines.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>"
        )
    lines.append("</ul>")

    # API Latency
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in data.api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )
    lines.append("</table>")

    # Active Sessions
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(data.active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Bootstrap / main
# ---------------------------------------------------------------------------


def _create_sample_log(log_file: str) -> None:
    """Create a sample *server.log* if one does not already exist."""
    path = Path(log_file)
    if path.exists():
        return
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
    """Orchestrate the ETL pipeline end-to-end."""
    config = Config.from_env()

    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )

    _create_sample_log(config.log_file)

    # ETL
    raw_entries = extract_logs(config.log_file)
    aggregated = transform_data(raw_entries)
    load_to_database(aggregated, config.db_path)
    generate_report(aggregated)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
