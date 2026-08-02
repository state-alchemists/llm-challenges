"""Server-log processing pipeline.

Extracts structured records from application logs, transforms them into
aggregated metrics (error counts, API latency averages, active sessions),
loads the results into a SQLite database, and generates an HTML report.

All configuration is read from environment variables so that no credentials
or paths are embedded in source code:

  LOG_FILE    – path to the server log file            (default: server.log)
  DB_PATH     – path to the SQLite metrics database     (default: metrics.db)
  DB_HOST     – database host (used for logging only)   (default: localhost)
  DB_PORT     – database port (used for logging only)   (default: 5432)
  DB_USER     – database user (used for logging only)   (default: admin)
  DB_PASS     – database password (used for logging only; default: empty)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Runtime configuration sourced from environment variables."""

    db_path: str = ""
    log_file: str = ""
    db_host: str = ""
    db_port: int = 0
    db_user: str = ""
    db_pass: str = ""

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables with sensible defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", ""),
        )


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str
    raw: str


@dataclass
class ErrorEntry(LogEntry):
    """An ERROR-level log entry."""

    message: str


@dataclass
class UserActionEntry(LogEntry):
    """An INFO log entry describing a user login/logout."""

    user_id: str
    action: str


@dataclass
class ApiCallEntry(LogEntry):
    """An INFO log entry describing an API call with its latency."""

    endpoint: str
    latency_ms: int


@dataclass
class WarnEntry(LogEntry):
    """A WARN-level log entry."""

    message: str


# Aggregation results ----------------------------------------------------------------

@dataclass
class ErrorSummary:
    """Count of occurrences per unique error message."""

    message_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class ApiLatencySummary:
    """Average latency per API endpoint."""

    endpoint_avgs: Dict[str, float] = field(default_factory=dict)


@dataclass
class SessionSummary:
    """Active user sessions remaining after processing all log lines."""

    active_users: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Log-line regex patterns
# ---------------------------------------------------------------------------

# "2024-01-01 12:00:00 INFO ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<lvl>\w+)\s+(?P<rest>.*)$"
)

# "... User <id> <action>"
_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")

# "... API <endpoint> took <N>ms"
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+.*?took\s+(?P<ms>\d+)ms$")


# ---------------------------------------------------------------------------
# Extract — read and parse log lines
# ---------------------------------------------------------------------------

def parse_log_lines(log_path: str) -> List[LogEntry]:
    """Read *log_path* and return a list of structured log entries.

    Lines that don't match the expected timestamp-level format are silently
    skipped.
    """
    entries: List[LogEntry] = []
    path = Path(log_path)
    if not path.exists():
        return entries

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _LOG_LINE_RE.match(line)
            if not m:
                continue

            ts = m.group("ts")
            lvl = m.group("lvl")
            rest = m.group("rest")
            raw = line

            if lvl == "ERROR":
                entries.append(ErrorEntry(timestamp=ts, level=lvl, raw=raw, message=rest))

            elif lvl == "INFO":
                um = _USER_RE.match(rest)
                if um:
                    entries.append(
                        UserActionEntry(
                            timestamp=ts,
                            level=lvl,
                            raw=raw,
                            user_id=um.group("uid"),
                            action=um.group("action"),
                        )
                    )
                    continue

                am = _API_RE.match(rest)
                if am:
                    entries.append(
                        ApiCallEntry(
                            timestamp=ts,
                            level=lvl,
                            raw=raw,
                            endpoint=am.group("endpoint"),
                            latency_ms=int(am.group("ms")),
                        )
                    )
                    continue

            elif lvl == "WARN":
                entries.append(WarnEntry(timestamp=ts, level=lvl, raw=raw, message=rest))

    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate into metrics
# ---------------------------------------------------------------------------

def transform(entries: List[LogEntry]) -> tuple[ErrorSummary, ApiLatencySummary, SessionSummary]:
    """Aggregate parsed entries into error counts, API latency averages, and live sessions.

    Returns:
        A 3-tuple of (ErrorSummary, ApiLatencySummary, SessionSummary).
    """
    error_counts: Dict[str, int] = {}
    endpoint_times: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}  # user_id -> login timestamp

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, UserActionEntry):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                del sessions[entry.user_id]

        elif isinstance(entry, ApiCallEntry):
            endpoint_times.setdefault(entry.endpoint, []).append(entry.latency_ms)

    endpoint_avgs = {
        ep: sum(times) / len(times) for ep, times in endpoint_times.items()
    }

    return (
        ErrorSummary(message_counts=error_counts),
        ApiLatencySummary(endpoint_avgs=endpoint_avgs),
        SessionSummary(active_users=dict(sessions)),
    )


# ---------------------------------------------------------------------------
# Load — persist to SQLite and generate HTML report
# ---------------------------------------------------------------------------

def load_to_db(
    cfg: Config,
    errors: ErrorSummary,
    api_latency: ApiLatencySummary,
) -> None:
    """Write aggregated metrics into the SQLite database at *cfg.db_path*.

    SQL values are passed as parameters — never interpolated — to prevent
    injection.
    """
    print(f"Connecting to {cfg.db_host}:{cfg.db_port} as {cfg.db_user}...")

    conn = sqlite3.connect(cfg.db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for msg, count in errors.message_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in api_latency.endpoint_avgs.items():
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    errors: ErrorSummary,
    api_latency: ApiLatencySummary,
    sessions: SessionSummary,
    output_path: str = "report.html",
) -> None:
    """Render an HTML report to *output_path*.

    The report contains three sections matching the original output:
    error summary, API latency table, and active session count.
    """
    lines: List[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")

    for err_msg, count in errors.message_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, avg in api_latency.endpoint_avgs.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(sessions.active_users)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    cfg = Config.from_env()

    # Extract
    entries = parse_log_lines(cfg.log_file)

    # Transform
    errors, api_latency, sessions = transform(entries)

    # Load
    load_to_db(cfg, errors, api_latency)
    generate_report(errors, api_latency, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # When the configured log file doesn't exist, create a sample one so the
    # pipeline can be demonstrated out of the box.
    cfg = Config.from_env()
    if not Path(cfg.log_file).exists():
        Path(cfg.log_file).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )

    run_pipeline()