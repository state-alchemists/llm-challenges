"""Process server logs into a SQLite database and an HTML report.

The pipeline follows an Extract -> Transform -> Load structure:

* **Extract** — read and regex-parse raw log lines into structured
  `LogEntry` records.
* **Transform** — aggregate entries into error counts, per-endpoint
  latency averages, and the active session count.
* **Load** — persist the aggregates to SQLite with parameterized
  queries and render ``report.html``.

All configuration (database path, log file path, report path, and
credentials) is read from environment variables.  No paths or secrets
are hardcoded:

=================  ===================  ==============================
Variable           Default              Purpose
=================  ===================  ==============================
``DB_PATH``        ``metrics.db``       SQLite database file
``LOG_FILE``       ``server.log``       Input server log file
``REPORT_FILE``    ``report.html``      Output HTML report
``DB_HOST``        ``localhost``        DB host (informational)
``DB_PORT``        ``5432``             DB port (informational)
``DB_USER``        ``admin``            DB user (informational)
``DB_PASS``        *(empty)*            DB password — never hardcoded
=================  ===================  ==============================
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_DB_PATH = "DB_PATH"
_ENV_LOG_FILE = "LOG_FILE"
_ENV_REPORT_FILE = "REPORT_FILE"
_ENV_DB_HOST = "DB_HOST"
_ENV_DB_PORT = "DB_PORT"
_ENV_DB_USER = "DB_USER"
_ENV_DB_PASS = "DB_PASS"


@dataclass(frozen=True)
class Config:
    """Runtime configuration, sourced from environment variables."""

    db_path: Path
    log_file: Path
    report_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Build a :class:`Config` from environment variables.

    Non-secret values fall back to the defaults above so the pipeline
    runs out of the box; the password has no default and must come
    from the environment.
    """
    return Config(
        db_path=Path(os.environ.get(_ENV_DB_PATH, "metrics.db")),
        log_file=Path(os.environ.get(_ENV_LOG_FILE, "server.log")),
        report_file=Path(os.environ.get(_ENV_REPORT_FILE, "report.html")),
        db_host=os.environ.get(_ENV_DB_HOST, "localhost"),
        db_port=int(os.environ.get(_ENV_DB_PORT, "5432")),
        db_user=os.environ.get(_ENV_DB_USER, "admin"),
        db_pass=os.environ.get(_ENV_DB_PASS, ""),
    )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+(?P<message>.+)$"
)
_USER_ACTION_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>.+)$")
_API_CALL_RE = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$"
)

_SAMPLE_LOG_LINES = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


@dataclass(frozen=True)
class LogEntry:
    """A single parsed log line.

    Only the fields relevant to the entry's kind are populated; the
    rest stay ``None``.  ``kind`` is one of ``"error"``, ``"warn"``,
    ``"user"`` or ``"api"``.
    """

    timestamp: str
    level: str
    kind: str
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


def parse_log_line(line: str) -> LogEntry | None:
    """Parse one log line into a :class:`LogEntry`.

    Returns ``None`` when the line does not match the expected
    ``<timestamp> <LEVEL> <message>`` shape or is an INFO line that
    carries neither a user action nor an API call.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if match is None:
        return None
    timestamp, level, message = match.group("timestamp", "level", "message")

    if level == "ERROR":
        return LogEntry(timestamp, level, "error", message=message)
    if level == "WARN":
        return LogEntry(timestamp, level, "warn", message=message)

    user_match = _USER_ACTION_RE.match(message)
    if user_match is not None:
        return LogEntry(
            timestamp, level, "user",
            user_id=user_match.group("user_id"),
            action=user_match.group("action"),
        )

    api_match = _API_CALL_RE.match(message)
    if api_match is not None:
        duration = api_match.group("duration_ms")
        return LogEntry(
            timestamp, level, "api",
            endpoint=api_match.group("endpoint"),
            duration_ms=int(duration) if duration is not None else 0,
        )

    return None


def read_log_entries(log_file: Path) -> list[LogEntry]:
    """Read the log file and parse every line into a :class:`LogEntry`."""
    entries: list[LogEntry] = []
    with open(log_file, encoding="utf-8") as handle:
        for line in handle:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


def ensure_log_exists(log_file: Path) -> None:
    """Create a sample log file when the configured one is missing.

    Preserves the original script's bootstrap behavior so the pipeline
    can be exercised end-to-end on a fresh checkout.
    """
    if not log_file.exists():
        log_file.write_text("\n".join(_SAMPLE_LOG_LINES) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def summarize_errors(entries: Iterable[LogEntry]) -> dict[str, int]:
    """Count how many times each error message appears."""
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.kind == "error" and entry.message is not None:
            counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def compute_latency_stats(entries: Iterable[LogEntry]) -> dict[str, float]:
    """Return the average latency in milliseconds for each API endpoint."""
    durations: dict[str, list[int]] = {}
    for entry in entries:
        if entry.kind == "api" and entry.endpoint is not None and entry.duration_ms is not None:
            durations.setdefault(entry.endpoint, []).append(entry.duration_ms)
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in durations.items()
    }


def count_active_sessions(entries: Iterable[LogEntry]) -> int:
    """Return how many users are still logged in after all events."""
    active: set[str] = set()
    for entry in entries:
        if entry.kind != "user" or entry.user_id is None or entry.action is None:
            continue
        if entry.action == "logged in":
            active.add(entry.user_id)
        elif entry.action == "logged out":
            active.discard(entry.user_id)
    return len(active)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(db_path: Path, errors: dict[str, int], latency: dict[str, float]) -> None:
    """Persist aggregated metrics into SQLite.

    All queries use ``?`` placeholders — values are bound by the
    driver, never interpolated into the SQL text.
    """
    now = datetime.datetime.now().isoformat(sep=" ")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        cursor.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            [(now, message, count) for message, count in errors.items()],
        )
        cursor.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            [(now, endpoint, avg_ms) for endpoint, avg_ms in latency.items()],
        )


def generate_report_html(
    errors: dict[str, int],
    latency: dict[str, float],
    active_sessions: int,
) -> str:
    """Render the aggregated metrics as an HTML report string."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in errors.items():
        lines.append(f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg_ms in latency.items():
        lines.append(f"<tr><td>{html.escape(endpoint)}</td><td>{avg_ms:.1f}</td></tr>")
    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines) + "\n"


def write_report(report_file: Path, content: str) -> None:
    """Write the rendered report to disk."""
    report_file.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract -> Transform -> Load pipeline."""
    config = load_config()
    ensure_log_exists(config.log_file)

    entries = read_log_entries(config.log_file)
    errors = summarize_errors(entries)
    latency = compute_latency_stats(entries)
    active_sessions = count_active_sessions(entries)

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")
    load_to_db(config.db_path, errors, latency)

    write_report(config.report_file, generate_report_html(errors, latency, active_sessions))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
