"""Process server logs into a metrics database and an HTML report.

The pipeline follows an Extract -> Transform -> Load (ETL) structure:

    Extract   read_log_entries()       read and regex-parse log lines
    Transform aggregate_error_counts() count ERROR occurrences per message
              extract_api_calls()      collect API call records from INFO lines
              compute_api_metrics()    average latency per endpoint
              count_active_sessions()  track logins/logouts, count live users
    Load      store_error_counts()     persist error counts (parameterized SQL)
              store_api_metrics()      persist latency metrics (parameterized SQL)
              render_report()          build the HTML report
              write_report()           write the report to disk

All configuration comes from environment variables — no credentials or paths
are hardcoded:

    DB_PATH       path to the SQLite database file   (default: metrics.db)
    LOG_FILE      path to the server log file        (default: server.log)
    REPORT_FILE   path to the HTML report            (default: report.html)
    DB_HOST       database host (connection metadata; SQLite ignores it)
    DB_PORT       database port (connection metadata; SQLite ignores it)
    DB_USER       database user (connection metadata; SQLite ignores it)
    DB_PASSWORD   database password (never logged or persisted)
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

# --- Configuration ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration, sourced entirely from environment variables."""

    db_path: Path
    log_file: Path
    report_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_password: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from the process environment, with safe defaults."""
        return cls(
            db_path=Path(os.getenv("DB_PATH", "metrics.db")),
            log_file=Path(os.getenv("LOG_FILE", "server.log")),
            report_file=Path(os.getenv("REPORT_FILE", "report.html")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_password=os.getenv("DB_PASSWORD", ""),
        )


# --- Extract ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str


_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN|DEBUG)\s+"
    r"(?P<message>.*)$"
)
_USER_ACTION_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>.+)$")
_API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")


def parse_log_line(line: str) -> LogEntry | None:
    """Parse one log line into a LogEntry, or None if it does not match."""
    match = _LOG_LINE_RE.match(line.strip())
    if match is None:
        return None
    return LogEntry(
        timestamp=match.group("timestamp"),
        level=match.group("level"),
        message=match.group("message"),
    )


def read_log_entries(log_file: Path) -> list[LogEntry]:
    """Read a log file and return all parseable entries in file order."""
    if not log_file.is_file():
        return []
    entries: list[LogEntry] = []
    with log_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


def ensure_log_file(log_file: Path) -> None:
    """Create a sample log file when the configured one is missing."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    if log_file.exists():
        return
    with log_file.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(sample_lines) + "\n")


# --- Transform --------------------------------------------------------------


def aggregate_error_counts(entries: list[LogEntry]) -> dict[str, int]:
    """Count how many times each ERROR message appeared, in first-seen order."""
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.level == "ERROR":
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A single observed API call."""

    endpoint: str
    duration_ms: int


def extract_api_calls(entries: list[LogEntry]) -> list[ApiCall]:
    """Pull API call records out of INFO log entries."""
    calls: list[ApiCall] = []
    for entry in entries:
        if entry.level != "INFO":
            continue
        match = _API_CALL_RE.match(entry.message)
        if match is None:
            continue
        duration = match.group("duration")
        calls.append(
            ApiCall(
                endpoint=match.group("endpoint"),
                duration_ms=int(duration) if duration is not None else 0,
            )
        )
    return calls


@dataclass(frozen=True, slots=True)
class ApiMetric:
    """Average latency observed for one endpoint."""

    endpoint: str
    avg_ms: float


def compute_api_metrics(calls: list[ApiCall]) -> list[ApiMetric]:
    """Average the observed latencies per endpoint, in first-seen order."""
    by_endpoint: dict[str, list[int]] = {}
    for call in calls:
        by_endpoint.setdefault(call.endpoint, []).append(call.duration_ms)
    return [
        ApiMetric(endpoint=endpoint, avg_ms=sum(times) / len(times))
        for endpoint, times in by_endpoint.items()
    ]


def count_active_sessions(entries: list[LogEntry]) -> int:
    """Count users currently logged in, honoring login/logout ordering."""
    active: set[str] = set()
    for entry in entries:
        if entry.level != "INFO":
            continue
        match = _USER_ACTION_RE.match(entry.message)
        if match is None:
            continue
        user_id = match.group("user_id")
        action = match.group("action")
        if "logged in" in action:
            active.add(user_id)
        elif "logged out" in action:
            active.discard(user_id)
    return len(active)


# --- Load -------------------------------------------------------------------


def connect_database(db_path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite database."""
    return sqlite3.connect(str(db_path))


def init_schema(connection: sqlite3.Connection) -> None:
    """Create the pipeline's tables if they do not exist yet."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def store_error_counts(
    connection: sqlite3.Connection, counts: dict[str, int], recorded_at: str
) -> None:
    """Persist error counts, one row per message, using parameterized SQL."""
    connection.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(recorded_at, message, count) for message, count in counts.items()],
    )


def store_api_metrics(
    connection: sqlite3.Connection, metrics: list[ApiMetric], recorded_at: str
) -> None:
    """Persist per-endpoint latency averages, using parameterized SQL."""
    connection.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(recorded_at, metric.endpoint, metric.avg_ms) for metric in metrics],
    )


def render_report(
    error_counts: dict[str, int],
    api_metrics: list[ApiMetric],
    active_session_count: int,
) -> str:
    """Build the HTML report; all dynamic content is HTML-escaped."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in error_counts.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for metric in api_metrics:
        lines.append(
            f"<tr><td>{html.escape(metric.endpoint)}</td>"
            f"<td>{round(metric.avg_ms, 1)}</td></tr>"
        )
    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines) + "\n"


def write_report(report_html: str, report_file: Path) -> None:
    """Write the rendered report to disk."""
    with report_file.open("w", encoding="utf-8") as handle:
        handle.write(report_html)


# --- Orchestration -----------------------------------------------------------


def main() -> None:
    """Run the full ETL pipeline and generate the report."""
    config = Config.from_env()
    ensure_log_file(config.log_file)

    entries = read_log_entries(config.log_file)
    error_counts = aggregate_error_counts(entries)
    api_metrics = compute_api_metrics(extract_api_calls(entries))
    active_session_count = count_active_sessions(entries)

    recorded_at = datetime.datetime.now().isoformat(sep=" ")
    print(
        f"Connecting to sqlite:{config.db_path} "
        f"(configured for {config.db_user}@{config.db_host}:{config.db_port})..."
    )
    with closing(connect_database(config.db_path)) as connection:
        init_schema(connection)
        store_error_counts(connection, error_counts, recorded_at)
        store_api_metrics(connection, api_metrics, recorded_at)
        connection.commit()

    report_html = render_report(error_counts, api_metrics, active_session_count)
    write_report(report_html, config.report_file)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
