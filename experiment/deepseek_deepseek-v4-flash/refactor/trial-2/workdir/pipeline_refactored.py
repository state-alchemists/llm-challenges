"""pipeline_refactored.py — Extract → Transform → Load pipeline for server logs.

Reads a server log file, derives error, API-latency and active-session
metrics, persists them to a SQLite database, and writes an HTML report
(``report.html``).

All configuration is read from environment variables at runtime:

* ``DB_PATH``  — SQLite database file (default ``metrics.db``)
* ``LOG_FILE`` — server log file to process (default ``server.log``)
* ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASS`` — connection metadata
  kept for parity with the original script; the local store is SQLite.
* ``REPORT_PATH`` — HTML report output (default ``report.html``)
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Runtime configuration, populated from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables, with safe defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", ""),
            report_path=os.getenv("REPORT_PATH", "report.html"),
        )


# ---------------------------------------------------------------------------
# Extraction: read the log file and parse each line with regexes
# ---------------------------------------------------------------------------

# Matches a full log line: ``YYYY-MM-DD HH:MM:SS LEVEL message...``
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) (?P<message>.+)$"
)
# Matches user actions: ``User <id> <action>`` (search anywhere in the message).
_USER_ACTION_RE = re.compile(r"User (?P<user_id>\S+)(?: (?P<action>.*))?$")
# Matches API calls: ``API <endpoint> [took <ms>ms]``.
_API_CALL_RE = re.compile(r"API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")

# Sample log used to seed a missing log file, mirroring the original script.
SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@dataclass
class LogEntry:
    """One parsed, normalized log record."""

    timestamp: str
    kind: str  # "ERROR" | "USER" | "API" | "WARN"
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


def seed_sample_log_if_missing(log_file: str) -> None:
    """Create a sample log file if none exists (original script behavior)."""
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(SAMPLE_LOG)


def parse_log_line(line: str) -> LogEntry | None:
    """Parse one log line into a LogEntry, or None if it does not match."""
    match = _LOG_LINE_RE.match(line.rstrip("\n"))
    if match is None:
        return None
    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return LogEntry(timestamp=timestamp, kind="ERROR", message=message)

    if level == "INFO":
        user_match = _USER_ACTION_RE.search(message)
        if user_match is not None:
            return LogEntry(
                timestamp=timestamp,
                kind="USER",
                message=message,
                user_id=user_match.group("user_id"),
                action=user_match.group("action") or "",
            )
        api_match = _API_CALL_RE.search(message)
        if api_match is not None:
            duration = api_match.group("duration")
            return LogEntry(
                timestamp=timestamp,
                kind="API",
                message=message,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(duration) if duration is not None else 0,
            )
        # Other INFO lines carry no tracked signal.
        return None

    if level == "WARN":
        return LogEntry(timestamp=timestamp, kind="WARN", message=message)

    # Unrecognized levels are ignored, as in the original script.
    return None


def extract_log_entries(log_file: str) -> list[LogEntry]:
    """Read the log file and return a list of parsed LogEntry records."""
    entries: list[LogEntry] = []
    path = Path(log_file)
    if not path.is_file():
        return entries
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform: derive report metrics from the extracted entries
# ---------------------------------------------------------------------------

@dataclass
class TransformResult:
    """Aggregated metrics consumed by the load stage."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]
    active_sessions: int


def transform_entries(entries: list[LogEntry]) -> TransformResult:
    """Aggregate entries into error counts, per-endpoint average latency,
    and the number of users currently logged in."""
    error_counts: dict[str, int] = {}
    sessions: dict[str, str] = {}
    endpoint_times: dict[str, list[int]] = {}

    for entry in entries:
        if entry.kind == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.kind == "USER":
            user_id = entry.user_id or ""
            if "logged in" in (entry.action or ""):
                sessions[user_id] = entry.timestamp
            elif "logged out" in (entry.action or "") and user_id in sessions:
                sessions.pop(user_id)
        elif entry.kind == "API":
            endpoint_times.setdefault(entry.endpoint or "", []).append(
                entry.duration_ms or 0
            )

    endpoint_avg_ms = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }
    return TransformResult(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load: persist metrics to SQLite and write the HTML report
# ---------------------------------------------------------------------------

def load_to_database(db_path: str, result: TransformResult) -> None:
    """Write aggregated metrics into the SQLite database using
    parameterized queries (no string interpolation of values)."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        processed_at = str(datetime.datetime.now())
        for message, count in result.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (processed_at, message, count),
            )
        for endpoint, avg_ms in result.endpoint_avg_ms.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (processed_at, endpoint, avg_ms),
            )
        conn.commit()
    finally:
        conn.close()


def generate_report(report_path: str, result: TransformResult) -> None:
    """Write report.html with the error summary, API latency table, and
    active session count. Log-derived values are HTML-escaped."""
    error_items = "\n".join(
        f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        for message, count in result.error_counts.items()
    )
    latency_rows = "\n".join(
        f"<tr><td>{html.escape(endpoint)}</td><td>"
        f"{round(avg_ms, 1)}</td></tr>"
        for endpoint, avg_ms in result.endpoint_avg_ms.items()
    )

    out = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        "<h1>Error Summary</h1>\n<ul>\n"
        + error_items
        + "\n</ul>\n"
        "<h2>API Latency</h2>\n<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        + latency_rows
        + "\n</table>\n"
        "<h2>Active Sessions</h2>\n"
        f"<p>{result.active_sessions} user(s) currently active</p>\n"
        "</body>\n</html>"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full extract → transform → load pipeline."""
    config = Config.from_env()
    seed_sample_log_if_missing(config.log_file)

    entries = extract_log_entries(config.log_file)
    result = transform_entries(entries)

    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )
    load_to_database(config.db_path, result)
    generate_report(config.report_path, result)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
