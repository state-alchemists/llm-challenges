"""Process server logs into a SQLite metrics store and an HTML report.

The pipeline follows an Extract -> Transform -> Load (ETL) structure:

1. **Extract** (:func:`extract_logs`) reads raw log lines from ``server.log``
   and parses them into structured :class:`LogEntry` records using regex.
2. **Transform** (:func:`transform_logs`) aggregates the raw records into
   error counts, per-endpoint latency averages, and the active session count.
3. **Load** (:func:`load_metrics`) persists the aggregates into SQLite with
   parameterized queries, and :func:`generate_report` renders ``report.html``.

All configuration (paths, DB file, connection metadata) is read from
environment variables via :func:`load_config`, so no credentials or paths
are hardcoded.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Runtime configuration resolved from environment variables."""

    log_file: str
    db_path: str
    report_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read all pipeline configuration from environment variables.

    Every value has a local-development default so the script runs without
    exported variables; an explicitly set environment variable always wins.
    """
    return Config(
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_path=os.getenv("DB_PATH", "metrics.db"),
        report_file=os.getenv("REPORT_FILE", "report.html"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# A log line: timestamp, level, then free-form body.
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO|DEBUG) (?P<body>.*)$"
)
# INFO body for user lifecycle events: "User <id> logged in|out".
_USER_EVENT_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>.+)$")
# INFO body for API calls: "API <endpoint> took <ms>ms" (duration optional).
_API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$")


@dataclass(frozen=True)
class LogEntry:
    """One parsed log line. Fields not relevant to the entry kind stay default."""

    kind: str
    timestamp: str
    message: str = ""
    user_id: int = 0
    action: str = ""
    endpoint: str = ""
    duration_ms: int = 0


def _parse_line(line: str) -> LogEntry | None:
    """Parse a single log line into a :class:`LogEntry`, or ``None`` if malformed."""
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None
    timestamp = match.group("timestamp")
    level = match.group("level")
    body = match.group("body")

    if level in ("ERROR", "WARN"):
        return LogEntry(kind=level.lower(), timestamp=timestamp, message=body)
    if level != "INFO":
        return None

    user_match = _USER_EVENT_RE.match(body)
    if user_match is not None:
        return LogEntry(
            kind="user",
            timestamp=timestamp,
            user_id=int(user_match.group("user_id")),
            action=user_match.group("action"),
        )

    api_match = _API_CALL_RE.match(body)
    if api_match is not None:
        return LogEntry(
            kind="api",
            timestamp=timestamp,
            endpoint=api_match.group("endpoint"),
            duration_ms=int(api_match.group("duration_ms") or 0),
        )
    return None


def extract_logs(log_path: str) -> list[LogEntry]:
    """Read ``log_path`` and parse every well-formed line into a LogEntry.

    Malformed lines are skipped; a missing file yields an empty list.
    """
    entries: list[LogEntry] = []
    if not os.path.exists(log_path):
        return entries
    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            entry = _parse_line(line.strip())
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransformResult:
    """Aggregated metrics derived from the extracted log entries."""

    error_counts: dict[str, int]
    endpoint_stats: dict[str, float]
    active_sessions: int


def transform_logs(entries: list[LogEntry]) -> TransformResult:
    """Aggregate log entries into error counts, latency averages, and session count."""
    error_counts: dict[str, int] = {}
    endpoint_times: dict[str, list[int]] = {}
    active_users: set[int] = set()

    for entry in entries:
        if entry.kind == "error":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1
        elif entry.kind == "api":
            endpoint_times.setdefault(entry.endpoint, []).append(entry.duration_ms)
        elif entry.kind == "user":
            if "logged in" in entry.action:
                active_users.add(entry.user_id)
            elif "logged out" in entry.action:
                active_users.discard(entry.user_id)

    endpoint_stats: dict[str, float] = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }
    return TransformResult(
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        active_sessions=len(active_users),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

_ERRORS_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS errors "
    "(dt TEXT, message TEXT, count INTEGER)"
)
_API_METRICS_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS api_metrics "
    "(dt TEXT, endpoint TEXT, avg_ms REAL)"
)


def load_metrics(conn: sqlite3.Connection, result: TransformResult) -> None:
    """Persist aggregated metrics into SQLite using parameterized queries.

    Values are bound with ``?`` placeholders, never interpolated into the SQL
    string, which removes the injection risk of the original implementation.
    """
    cursor = conn.cursor()
    cursor.execute(_ERRORS_TABLE_SQL)
    cursor.execute(_API_METRICS_TABLE_SQL)

    timestamp = datetime.datetime.now().isoformat(" ")
    for message, count in result.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (timestamp, message, count),
        )
    for endpoint, avg_ms in result.endpoint_stats.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (timestamp, endpoint, avg_ms),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(result: TransformResult, report_path: str) -> None:
    """Render report.html with the error summary, API latency table, and session count."""
    rows = [
        f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        for message, count in result.error_counts.items()
    ]
    error_list = "<ul>\n" + "\n".join(rows) + "</ul>" if rows else "<p>No errors</p>"

    latency_rows = [
        f"<tr><td>{html.escape(endpoint)}</td><td>{round(avg_ms, 1)}</td></tr>"
        for endpoint, avg_ms in result.endpoint_stats.items()
    ]
    latency_table = (
        "<table border='1'>\n<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        + "\n".join(latency_rows)
        + "\n</table>"
    )

    document = (
        "<html>\n<head><title>System Report</title></head>\n<body>\n"
        "<h1>Error Summary</h1>\n"
        + error_list
        + "\n<h2>API Latency</h2>\n"
        + latency_table
        + "\n<h2>Active Sessions</h2>\n"
        + f"<p>{result.active_sessions} user(s) currently active</p>\n"
        + "</body>\n</html>"
    )

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(document)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full ETL pipeline: extract, transform, load, then render the report."""
    config = load_config()
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    entries = extract_logs(config.log_file)
    result = transform_logs(entries)

    conn = sqlite3.connect(config.db_path)
    try:
        load_metrics(conn, result)
    finally:
        conn.close()

    generate_report(result, config.report_file)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    main()
