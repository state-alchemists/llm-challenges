"""Pipeline: Extract server logs -> Transform into metrics -> Load into DB and report.

Usage:
    python pipeline_refactored.py

Environment variables (all optional with sensible defaults):
    LOG_FILE    Path to server log file          (default: server.log)
    DB_PATH     Path to SQLite database           (default: metrics.db)
    DB_HOST     Database hostname (informational) (default: localhost)
    DB_PORT     Database port (informational)     (default: 5432)
    DB_USER     Database user (informational)     (default: admin)
    DB_PASS     Database password (informational) (default: password123)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# ===========================================================================
# Configuration
# ===========================================================================


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Runtime configuration sourced from environment variables."""

    log_file: Path
    db_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Load configuration from environment variables with sensible defaults.
        
        Every value can be overridden via its uppercase environment variable.
        DB_HOST/DB_PORT/DB_USER/DB_PASS are retained for compatibility but are
        unused by the SQLite backend.
        """
        return cls(
            log_file=Path(os.environ.get("LOG_FILE", "server.log")),
            db_path=Path(os.environ.get("DB_PATH", "metrics.db")),
            db_host=os.environ.get("DB_HOST", "localhost"),
            db_port=int(os.environ.get("DB_PORT", "5432")),
            db_user=os.environ.get("DB_USER", "admin"),
            db_pass=os.environ.get("DB_PASS", "password123"),
        )


# ===========================================================================
# Data types
# ===========================================================================


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single parsed log line with typed fields per log level.

    Fields are contextual: ERROR/WARN fill *message*; USER fills *user_id*
    and *user_action*; API fills *endpoint* and *duration_ms*.
    """

    timestamp: str
    level: str
    message: str = ""
    # User-specific
    user_id: str = ""
    user_action: str = ""
    # API-specific
    endpoint: str = ""
    duration_ms: int = 0


# ===========================================================================
# Extract: Read and parse the log file
# ===========================================================================

# Matches the common prefix: timestamp + level + message body.
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|WARN|INFO)\s+"
    r"(?P<msg>.+)$",
)

# Sub-patterns applied against the message body.
_USER_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>/\S+) took (?P<dur>\d+)ms$")


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a ``LogEntry``.

    Returns ``None`` when the line doesn't match any known format.
    """
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None

    ts = m.group("ts")
    level = m.group("level")
    msg = m.group("msg")

    if level in ("ERROR", "WARN"):
        return LogEntry(timestamp=ts, level=level, message=msg)

    if level == "INFO":
        # Try user event (login / logout).
        if (um := _USER_RE.match(msg)):
            return LogEntry(
                timestamp=ts,
                level=level,
                message=msg,
                user_id=um.group("uid"),
                user_action=um.group("action"),
            )
        # Try API latency line.
        if (am := _API_RE.match(msg)):
            return LogEntry(
                timestamp=ts,
                level=level,
                message=msg,
                endpoint=am.group("endpoint"),
                duration_ms=int(am.group("dur")),
            )
        # Generic INFO entry.
        return LogEntry(timestamp=ts, level=level, message=msg)

    return None


def read_log_entries(path: Path) -> list[LogEntry]:
    """Read and parse every line in the log file.

    Silently skips blank lines and unrecognised formats.
    """
    if not path.exists():
        return []

    entries: list[LogEntry] = []
    with open(path, "r") as f:
        for line in f:
            stripped = line.rstrip("\n\r")
            if not stripped:
                continue
            entry = parse_log_line(stripped)
            if entry is not None:
                entries.append(entry)
    return entries


def ensure_sample_log(path: Path) -> None:
    """Create a sample log file if one doesn't already exist.

    This reproduces the original inline seed data so the pipeline is
    runnable out of the box.
    """
    if path.exists():
        return
    sample = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    with open(path, "w") as f:
        f.write(sample)


# ===========================================================================
# Transform: Derive metrics from parsed entries
# ===========================================================================


def aggregate_error_counts(entries: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each unique error message.

    Returns a dict mapping message text to occurrence count, ordered by
    first appearance in the log.
    """
    counts: dict[str, int] = {}
    for e in entries:
        if e.level == "ERROR":
            # Preserve insertion order (Python 3.7+).
            if e.message not in counts:
                counts[e.message] = 0
            counts[e.message] += 1
    return counts


def summarize_api_latency(entries: list[LogEntry]) -> dict[str, float]:
    """Compute the average latency per API endpoint.

    Returns a dict mapping endpoint path to its average duration in
    milliseconds, rounded to one decimal place.
    """
    totals: dict[str, list[int]] = {}
    for e in entries:
        if e.level == "INFO" and e.endpoint:
            totals.setdefault(e.endpoint, []).append(e.duration_ms)

    averages: dict[str, float] = {}
    for endpoint, times in totals.items():
        avg = sum(times) / len(times)
        averages[endpoint] = round(avg, 1)
    return averages


def compute_active_sessions(entries: list[LogEntry]) -> set[str]:
    """Determine currently active user sessions by replaying login/logout events.

    Returns the set of user IDs whose session is still active at the end of
    the log.
    """
    active: dict[str, str] = {}
    for e in entries:
        if e.level != "INFO" or not e.user_id:
            continue
        if "logged in" in e.user_action:
            active[e.user_id] = e.timestamp
        elif "logged out" in e.user_action and e.user_id in active:
            del active[e.user_id]
    return set(active.keys())


# ===========================================================================
# Load: Persist metrics and generate the report
# ===========================================================================

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS errors (
    dt TEXT,
    message TEXT,
    count INTEGER
);
CREATE TABLE IF NOT EXISTS api_metrics (
    dt TEXT,
    endpoint TEXT,
    avg_ms REAL
);
"""


def _init_db(conn: sqlite3.Connection) -> None:
    """Ensure the target tables exist."""
    conn.executescript(_DB_SCHEMA)


def store_metrics(
    conn: sqlite3.Connection,
    error_counts: dict[str, int],
    api_stats: dict[str, float],
) -> None:
    """Persist aggregated metrics into the database using parameterized queries.

    Args:
        conn: Open SQLite connection (caller manages commit/close).
        error_counts: Mapping of error message -> occurrence count.
        api_stats: Mapping of endpoint -> average latency in ms.
    """
    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_stats.items():
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )


def build_report_html(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    active_sessions: set[str],
) -> str:
    """Generate the ``report.html`` document with the three required sections."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        # Escape minimal HTML in error messages to prevent injection.
        safe_msg = _escape_html(err_msg)
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg_ms in api_stats.items():
        lines.append(f"<tr><td>{_escape_html(endpoint)}</td><td>{avg_ms}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Escape HTML special characters to prevent injection in the report."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_report(path: Path, html: str) -> None:
    """Write the HTML report to disk."""
    with open(path, "w") as f:
        f.write(html)


# ===========================================================================
# Orchestration
# ===========================================================================


def run_pipeline(config: PipelineConfig) -> None:
    """Execute the full Extract -> Transform -> Load pipeline.

    Args:
        config: Pipeline configuration loaded from the environment.
    """
    # --- Extract ---
    ensure_sample_log(config.log_file)
    entries = read_log_entries(config.log_file)

    # --- Transform ---
    error_counts = aggregate_error_counts(entries)
    api_stats = summarize_api_latency(entries)
    active_sessions = compute_active_sessions(entries)

    # --- Load: database ---
    conn = sqlite3.connect(str(config.db_path))
    try:
        _init_db(conn)
        store_metrics(conn, error_counts, api_stats)
        conn.commit()
    finally:
        conn.close()

    # --- Load: report ---
    html = build_report_html(error_counts, api_stats, active_sessions)
    write_report(Path("report.html"), html)


def main() -> None:
    """Entry point: load config and run the pipeline."""
    config = PipelineConfig.from_env()
    run_pipeline(config)
    print(f"Pipeline finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
