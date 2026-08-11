"""Server-log pipeline: extract log entries, transform into metrics, load into DB + HTML report.

Environment variables
---------------------
DB_PATH      : Path to the SQLite database file        (default: "metrics.db")
LOG_FILE     : Path to the server log file              (default: "server.log")
DB_HOST      : Database host for connection logging      (default: "localhost")
DB_PORT      : Database port for connection logging      (default: "5432")
DB_USER      : Database user for connection logging      (default: "admin")
DB_PASS      : Database password for connection logging  (default: "password123")
REPORT_PATH  : Output path for the HTML report           (default: "report.html")
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
# Configuration — every value is overridable via environment variables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Immutable pipeline configuration sourced from environment variables."""

    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")
    report_path: str = os.getenv("REPORT_PATH", "report.html")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """An ERROR-level log line."""
    timestamp: str
    message: str


@dataclass
class UserAction:
    """A user login/logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with latency measurement."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarningEntry:
    """A WARN-level log line."""
    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """All structured data extracted from the server log."""
    errors: List[ErrorEntry] = field(default_factory=list)
    user_actions: List[UserAction] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[WarningEntry] = field(default_factory=list)


@dataclass
class Metrics:
    """Aggregated report-ready metrics derived from parsed log data."""
    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latency: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# Generic line: "2024-01-01 12:05:00 LEVEL ..."
_LOG_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<rest>.*)$")

# ERROR line rest is just the message.

# User action: "User <id> <action>"
_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")

# API call: "API <endpoint> took <n>ms"
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$", re.IGNORECASE)

# WARN line rest is just the message.


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(log_path: str) -> ParsedLog:
    """Parse the server log file into structured records.

    Uses regex to robustly match each log-line format. Lines that do not
    match the expected pattern are silently skipped.

    Args:
        log_path: Path to the server log file.

    Returns:
        A :class:`ParsedLog` containing errors, user actions, API calls,
        and warnings found in the log.
    """
    parsed = ParsedLog()
    path = Path(log_path)

    if not path.exists():
        return parsed

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            m = _LOG_RE.match(line)
            if not m:
                continue

            ts = m.group("ts")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                parsed.errors.append(ErrorEntry(timestamp=ts, message=rest))

            elif level == "WARN":
                parsed.warnings.append(WarningEntry(timestamp=ts, message=rest))

            elif level == "INFO":
                # Try user-action pattern first
                um = _USER_RE.match(rest)
                if um:
                    uid = um.group("uid")
                    action = um.group("action").strip()
                    parsed.user_actions.append(
                        UserAction(timestamp=ts, user_id=uid, action=action)
                    )
                    continue

                # Then API-call pattern
                am = _API_RE.match(rest)
                if am:
                    endpoint = am.group("endpoint")
                    latency = int(am.group("ms")) if am.group("ms") else 0
                    parsed.api_calls.append(
                        ApiCall(timestamp=ts, endpoint=endpoint, latency_ms=latency)
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(parsed: ParsedLog) -> Metrics:
    """Aggregate raw log entries into report-ready summaries.

    Produces:
      - error_counts:  mapping of error message → occurrence count
      - api_latency:    mapping of endpoint → list of latency values
      - active_sessions: count of users currently logged in

    Args:
        parsed: Structured log data from :func:`extract`.

    Returns:
        A :class:`Metrics` containing aggregated error counts, API
        latencies, and the active session count.
    """
    # Error summary — count occurrences per message
    error_counts: Dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    # API latency — collect per-endpoint latency lists
    api_latency: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.latency_ms)

    # Active sessions — track login/logout per user
    sessions: Dict[str, str] = {}  # user_id → login timestamp
    for action in parsed.user_actions:
        uid = action.user_id
        if "logged in" in action.action:
            sessions[uid] = action.timestamp
        elif "logged out" in action.action and uid in sessions:
            del sessions[uid]

    return Metrics(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — database
# ---------------------------------------------------------------------------

def load_to_db(
    config: Config,
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics into the SQLite database.

    Uses parameterised queries exclusively — no string formatting in SQL.

    Args:
        config:          Pipeline configuration (supplies ``db_path``, etc.).
        error_counts:    Mapping of error message → count.
        api_latency:     Mapping of endpoint → list of latency values.
    """
    now = datetime.datetime.now().isoformat(" ")

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Insert error summary — parameterised query
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    # Insert API latency averages — parameterised query
    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Load — HTML report
# ---------------------------------------------------------------------------

def generate_report(
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions: int,
) -> str:
    """Render an HTML report from aggregated metrics.

    The output includes an error summary, API latency table, and active
    session count — matching the original ``report.html`` structure.

    Args:
        error_counts:     Mapping of error message → count.
        api_latency:      Mapping of endpoint → list of latency values.
        active_sessions:  Number of currently active sessions.

    Returns:
        The complete HTML report as a string.
    """
    parts: List[str] = []
    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")

    # Error summary
    parts.append("<h1>Error Summary</h1>")
    parts.append("<ul>")
    for msg, count in error_counts.items():
        parts.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    parts.append("</ul>")

    # API latency table
    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        parts.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    parts.append("</table>")

    # Active sessions
    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{active_sessions} user(s) currently active</p>")

    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def write_report(report_html: str, report_path: str) -> None:
    """Write the HTML report to disk.

    Args:
        report_html: The complete HTML content.
        report_path: Destination file path.
    """
    Path(report_path).write_text(report_html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config: Optional[Config] = None) -> None:
    """Execute the full Extract → Transform → Load pipeline.

    1. **Extract** — parse the log file into structured records.
    2. **Transform** — aggregate into error counts, API latencies, and
       active sessions.
    3. **Load** — persist to the database and write the HTML report.

    Args:
        config: Pipeline configuration.  Defaults to values from
                environment variables (see :class:`Config`).
    """
    if config is None:
        config = Config()

    # Extract
    parsed = extract(config.log_file)

    # Transform
    metrics = transform(parsed)

    # Load
    load_to_db(config, metrics.error_counts, metrics.api_latency)

    report_html = generate_report(
        error_counts=metrics.error_counts,
        api_latency=metrics.api_latency,
        active_sessions=metrics.active_sessions,
    )
    write_report(report_html, config.report_path)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = Config()

    # Create a sample log file when none exists (mirrors original behaviour)
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

    run_pipeline(cfg)