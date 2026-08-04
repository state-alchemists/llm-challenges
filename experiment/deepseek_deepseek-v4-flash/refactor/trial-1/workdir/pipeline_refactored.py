"""Server-log reporting pipeline (refactored).

Extracts events from a server log, transforms them into aggregate stats,
and loads the results into a SQLite database plus an HTML report.

Pipeline stages
---------------
1. Extract: :func:`extract_events` parses each log line into a
   :class:`LogEvent` using regular expressions.
2. Transform: :func:`transform` derives error counts, per-endpoint
   latency averages, and the active session count.
3. Load: :func:`load_summary` persists the aggregates to SQLite with
   parameterized queries; :func:`render_report` and :func:`write_report`
   emit ``report.html``.

All configuration comes from environment variables; see :func:`load_config`.
"""

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Config:
    """Pipeline configuration sourced from environment variables."""

    db_path: Path
    log_path: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(frozen=True, slots=True)
class LogEvent:
    """One structured record parsed from a log line."""

    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ErrorStat:
    """Aggregated occurrence count for one distinct error message."""

    message: str
    count: int


@dataclass(frozen=True, slots=True)
class ApiStat:
    """Aggregated latency for one API endpoint."""

    endpoint: str
    avg_ms: float


@dataclass(frozen=True, slots=True)
class ReportData:
    """Everything the database and the HTML report need."""

    errors: list[ErrorStat]
    api_stats: list[ApiStat]
    active_sessions: int


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<message>.+?)\s*$"
)
_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+?)\s*$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?\s*$")


def parse_log_line(line: str) -> LogEvent | None:
    """Parse one log line into a :class:`LogEvent`, or ``None`` if unrecognized.

    Expected format: ``YYYY-MM-DD HH:MM:SS LEVEL message``.

    INFO payloads are interpreted as a user event (``User <id> <action>``)
    or an API call (``API <endpoint> took <ms>ms``); user events take
    precedence, matching the original script. An API line without a
    duration counts as 0 ms.
    """
    match = _LOG_LINE_RE.match(line)
    if match is None:
        return None

    timestamp = match.group("ts")
    level = match.group("level")
    message = match.group("message")

    if level == "INFO":
        user_match = _USER_RE.match(message)
        if user_match is not None:
            return LogEvent(
                timestamp=timestamp,
                level=level,
                message=message,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )
        api_match = _API_RE.match(message)
        if api_match is not None:
            duration = api_match.group("duration")
            return LogEvent(
                timestamp=timestamp,
                level=level,
                message=message,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(duration) if duration is not None else 0,
            )
        return None

    return LogEvent(timestamp=timestamp, level=level, message=message)


def extract_events(log_path: Path) -> Iterator[LogEvent]:
    """Yield a :class:`LogEvent` for every parseable line of the log file.

    A missing log file yields no events; it is not an error.
    """
    if not log_path.exists():
        return
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = parse_log_line(line)
            if event is not None:
                yield event


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def _count_errors(events: Iterable[LogEvent]) -> dict[str, int]:
    """Count occurrences of each distinct error message, in first-seen order."""
    counts: dict[str, int] = {}
    for event in events:
        if event.level == "ERROR":
            counts[event.message] = counts.get(event.message, 0) + 1
    return counts


def _aggregate_api_latencies(events: Iterable[LogEvent]) -> dict[str, list[int]]:
    """Collect per-endpoint latency samples, in first-seen order."""
    latencies: dict[str, list[int]] = {}
    for event in events:
        if event.endpoint is None or event.duration_ms is None:
            continue
        latencies.setdefault(event.endpoint, []).append(event.duration_ms)
    return latencies


def _track_sessions(events: Iterable[LogEvent]) -> dict[str, str]:
    """Replay login/logout events, returning currently-active users.

    Maps user id to the timestamp of their most recent login.
    """
    sessions: dict[str, str] = {}
    for event in events:
        if event.user_id is None or event.action is None:
            continue
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            del sessions[event.user_id]
    return sessions


def transform(events: Iterable[LogEvent]) -> ReportData:
    """Aggregate events into the stats the database and report need."""
    error_counts = _count_errors(events)
    endpoint_times = _aggregate_api_latencies(events)
    sessions = _track_sessions(events)

    return ReportData(
        errors=[
            ErrorStat(message=message, count=count)
            for message, count in error_counts.items()
        ],
        api_stats=[
            ApiStat(endpoint=endpoint, avg_ms=sum(times) / len(times))
            for endpoint, times in endpoint_times.items()
        ],
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_summary(config: Config, data: ReportData) -> None:
    """Persist aggregate stats to SQLite using parameterized queries.

    Rows are stamped with the processing time (``datetime.now()``),
    preserving the original script's behavior; the log's event time is
    not written to the database.
    """
    with sqlite3.connect(config.db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        conn.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (
                (str(datetime.datetime.now()), error.message, error.count)
                for error in data.errors
            ),
        )
        conn.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (
                (str(datetime.datetime.now()), stat.endpoint, stat.avg_ms)
                for stat in data.api_stats
            ),
        )


def render_report(data: ReportData) -> str:
    """Render the aggregate stats as the ``report.html`` document.

    Error messages and endpoints are HTML-escaped so log contents cannot
    inject markup into the report.
    """
    lines = [
        "<html>\n<head><title>System Report</title></head>\n<body>\n",
        "<h1>Error Summary</h1>\n<ul>\n",
    ]
    for error in data.errors:
        lines.append(
            f"<li><b>{html.escape(error.message)}</b>: "
            f"{error.count} occurrences</li>\n"
        )
    lines.append("</ul>\n")
    lines.append("<h2>API Latency</h2>\n<table border='1'>\n")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n")
    for stat in data.api_stats:
        lines.append(
            f"<tr><td>{html.escape(stat.endpoint)}</td>"
            f"<td>{round(stat.avg_ms, 1)}</td></tr>\n"
        )
    lines.append("</table>\n")
    lines.append("<h2>Active Sessions</h2>\n")
    lines.append(f"<p>{data.active_sessions} user(s) currently active</p>\n")
    lines.append("</body>\n</html>")
    return "".join(lines)


def write_report(report_path: Path, document: str) -> None:
    """Write the rendered HTML document to ``report_path``."""
    report_path.write_text(document, encoding="utf-8")


# ---------------------------------------------------------------------------
# Configuration and entry point
# ---------------------------------------------------------------------------


def load_config() -> Config:
    """Read all pipeline configuration from environment variables.

    Every value has a default so the script runs out of the box; set the
    variable to override it:

    - ``DB_PATH`` — SQLite database file (default ``metrics.db``)
    - ``LOG_FILE`` — server log to process (default ``server.log``)
    - ``REPORT_PATH`` — HTML output file (default ``report.html``)
    - ``DB_HOST`` / ``DB_PORT`` / ``DB_USER`` / ``DB_PASS`` — server
      credentials kept for parity with the original script. SQLite does
      not use them; they are read from the environment so no credential
      is hardcoded.
    """
    return Config(
        db_path=Path(os.environ.get("DB_PATH", "metrics.db")),
        log_path=Path(os.environ.get("LOG_FILE", "server.log")),
        report_path=Path(os.environ.get("REPORT_PATH", "report.html")),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_user=os.environ.get("DB_USER", "admin"),
        db_pass=os.environ.get("DB_PASS", ""),
    )


_SAMPLE_LOG = [
    "2024-01-01 12:00:00 INFO User 42 logged in\n",
    "2024-01-01 12:05:00 ERROR Database timeout\n",
    "2024-01-01 12:05:05 ERROR Database timeout\n",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
    "2024-01-01 12:10:00 INFO User 42 logged out\n",
]


def ensure_sample_log(log_path: Path) -> None:
    """Create the demo log file when none exists (kept from the original)."""
    if not log_path.exists():
        log_path.write_text("".join(_SAMPLE_LOG), encoding="utf-8")


def main(config: Config) -> None:
    """Run the full pipeline: extract, transform, load, render."""
    print(f"Processing {config.log_path}...")
    events = list(extract_events(config.log_path))

    data = transform(events)
    load_summary(config, data)
    print(f"Wrote summary to SQLite database {config.db_path}")

    write_report(config.report_path, render_report(data))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    cfg = load_config()
    ensure_sample_log(cfg.log_path)
    main(cfg)
