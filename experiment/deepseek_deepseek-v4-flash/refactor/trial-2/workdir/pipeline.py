"""Process server logs into a SQLite metrics database and an HTML report.

The pipeline follows an Extract -> Transform -> Load structure:

1. Extract: ``extract_log_entries`` parses each log line with a regular
   expression into a structured :class:`LogEntry`.
2. Transform: ``transform_log_entries`` aggregates the entries into an
   error summary, per-endpoint API latency statistics, and the set of
   currently active sessions.
3. Load: ``load_errors`` / ``load_api_metrics`` persist the aggregates
   with parameterized queries, and ``render_report`` / ``write_report``
   produce the ``report.html`` output.

All configuration is read from environment variables (see
:func:`load_config`); the literals in this module are only local
development defaults.
"""

from __future__ import annotations

import datetime as dt
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO|DEBUG) (?P<msg>.+)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?(?:\s.*)?$")

SAMPLE_LOG = """\
2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Database timeout
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
"""


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One structured record parsed from a server log line."""

    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ApiStat:
    """Average latency for a single API endpoint."""

    endpoint: str
    avg_ms: float


@dataclass(frozen=True, slots=True)
class ReportData:
    """Aggregates produced by the transform stage, ready to be loaded."""

    errors: dict[str, int]
    api_stats: list[ApiStat]
    active_session_count: int


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Resolved runtime configuration."""

    log_path: Path
    db_path: Path
    report_path: Path
    db_host: str
    db_port: str
    db_user: str
    db_pass: str


def load_config() -> PipelineConfig:
    """Read pipeline configuration from environment variables.

    The values passed to ``os.getenv`` are only defaults for local
    development; the environment wins at runtime. ``db_host``, ``db_port``,
    ``db_user`` and ``db_pass`` are reserved for a server-backed database —
    the SQLite backend used here does not need credentials.
    """
    return PipelineConfig(
        log_path=Path(os.getenv("LOG_FILE", "server.log")),
        db_path=Path(os.getenv("DB_PATH", "metrics.db")),
        report_path=Path(os.getenv("REPORT_FILE", "report.html")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=os.getenv("DB_PORT", "5432"),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: Path) -> list[LogEntry]:
    """Parse the server log into structured entries.

    Returns an empty list when the log file does not exist. Blank or
    malformed lines are skipped rather than crashing the pipeline.
    """
    entries: list[LogEntry] = []
    if not log_path.is_file():
        return entries
    with log_path.open(encoding="utf-8") as log_file:
        for line in log_file:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line, or return ``None`` if it is unparseable.

    The expected format is ``YYYY-MM-DD HH:MM:SS LEVEL MESSAGE``. INFO
    lines are further classified into user actions
    (``User <id> <action>``) and API calls
    (``API <endpoint> took <milliseconds>ms``).
    """
    stripped = line.strip()
    if not stripped:
        return None
    match = _LOG_LINE_RE.match(stripped)
    if match is None:
        return None
    timestamp = match.group("ts")
    level = match.group("level")
    message = match.group("msg").strip()
    if level != "INFO":
        return LogEntry(timestamp=timestamp, level=level, message=message)

    user_match = _USER_RE.match(message)
    if user_match is not None:
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            user_id=user_match.group("uid"),
            action=user_match.group("action").strip(),
        )

    api_match = _API_RE.match(message)
    if api_match is not None:
        raw_ms = api_match.group("ms")
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            endpoint=api_match.group("endpoint"),
            latency_ms=int(raw_ms) if raw_ms is not None else 0,
        )

    return LogEntry(timestamp=timestamp, level=level, message=message)


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_log_entries(entries: list[LogEntry]) -> ReportData:
    """Aggregate parsed entries into the data needed for the report."""
    return ReportData(
        errors=aggregate_errors(entries),
        api_stats=compute_api_stats(entries),
        active_session_count=len(track_active_sessions(entries)),
    )


def aggregate_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each error message, in first-seen order."""
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.level == "ERROR":
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def compute_api_stats(entries: list[LogEntry]) -> list[ApiStat]:
    """Compute the average latency per API endpoint, in first-seen order."""
    latencies: dict[str, list[int]] = {}
    for entry in entries:
        if entry.endpoint is None:
            continue
        latencies.setdefault(entry.endpoint, []).append(entry.latency_ms or 0)
    return [
        ApiStat(endpoint=endpoint, avg_ms=sum(times) / len(times))
        for endpoint, times in latencies.items()
    ]


def track_active_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """Track logins/logouts and return the currently active sessions.

    The returned mapping is user id -> login timestamp.
    """
    sessions: dict[str, str] = {}
    for entry in entries:
        if entry.user_id is None or entry.action is None:
            continue
        if "logged in" in entry.action:
            sessions[entry.user_id] = entry.timestamp
        elif "logged out" in entry.action and entry.user_id in sessions:
            del sessions[entry.user_id]
    return sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def init_db(db_path: Path) -> sqlite3.Connection:
    """Open the SQLite database, creating the schema when necessary."""
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
    return conn


def load_errors(
    conn: sqlite3.Connection, run_timestamp: str, errors: dict[str, int]
) -> None:
    """Insert the error summary into the ``errors`` table.

    Uses a parameterized query, so log-derived messages can never alter
    the SQL statement.
    """
    rows = [(run_timestamp, message, count) for message, count in errors.items()]
    with conn:
        conn.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", rows
        )


def load_api_metrics(
    conn: sqlite3.Connection, run_timestamp: str, api_stats: list[ApiStat]
) -> None:
    """Insert per-endpoint average latencies into the ``api_metrics`` table."""
    rows = [(run_timestamp, stat.endpoint, stat.avg_ms) for stat in api_stats]
    with conn:
        conn.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", rows
        )


def render_report(data: ReportData) -> str:
    """Render the HTML report: error summary, API latency table, sessions."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in data.errors.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines += [
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for stat in data.api_stats:
        lines.append(
            f"<tr><td>{html.escape(stat.endpoint)}</td>"
            f"<td>{round(stat.avg_ms, 1)}</td></tr>"
        )
    lines += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{data.active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    return "\n".join(lines)


def write_report(report_path: Path, report_html: str) -> None:
    """Persist the rendered report to disk."""
    report_path.write_text(report_html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline(config: PipelineConfig) -> None:
    """Run the extract -> transform -> load pipeline end to end."""
    entries = extract_log_entries(config.log_path)
    data = transform_log_entries(entries)

    print(f"Connected to SQLite database at {config.db_path}")
    conn = init_db(config.db_path)
    try:
        run_timestamp = dt.datetime.now().isoformat(sep=" ", timespec="seconds")
        load_errors(conn, run_timestamp, data.errors)
        load_api_metrics(conn, run_timestamp, data.api_stats)
    finally:
        conn.close()

    write_report(config.report_path, render_report(data))
    print(f"Job finished at {dt.datetime.now()}")


def ensure_sample_log(log_path: Path) -> None:
    """Write a sample log when none exists so the pipeline runs standalone."""
    if log_path.exists():
        return
    log_path.write_text(SAMPLE_LOG, encoding="utf-8")


def main() -> None:
    """Entry point: resolve config, seed a sample log if needed, run the pipeline."""
    config = load_config()
    ensure_sample_log(config.log_path)
    run_pipeline(config)


if __name__ == "__main__":
    main()
