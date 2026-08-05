"""Server-log pipeline: extract, transform, load.

Reads server logs, computes error summaries / API latency / active sessions,
persists results to SQLite, and writes an HTML report.

All configuration is read from environment variables with sensible defaults.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration — all overridable via environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("PIPELINE_LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("PIPELINE_REPORT_PATH", "report.html")
DB_HOST: str = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.getenv("PIPELINE_DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# General: "2024-01-01 12:00:00 LEVEL rest…"
_RE_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<payload>.+)$"
)

# INFO User <id> <action>
_RE_USER = re.compile(
    r"^User (?P<uid>\S+)\s+(?P<action>.+)$"
)

# INFO API <endpoint> took <n>ms
_RE_API = re.compile(
    r"^API (?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    """A single ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user login / logout event."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with measured latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarningEvent:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class LogData:
    """Aggregated results from log extraction."""

    errors: List[ErrorEvent] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[WarningEvent] = field(default_factory=list)


@dataclass
class TransformedData:
    """Analysis-ready summaries derived from raw log data."""

    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latency: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Extract — parse raw log lines into structured data
# ---------------------------------------------------------------------------


def extract(log_path: str) -> LogData:
    """Parse the server log file into structured event lists.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ``LogData`` containing categorised, typed events.
    """
    data = LogData()
    path = Path(log_path)

    if not path.exists():
        print(f"Log file not found: {log_path}")
        return data

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = _RE_LOG.match(line.strip())
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            payload = match.group("payload")

            if level == "ERROR":
                data.errors.append(ErrorEvent(timestamp=timestamp, message=payload))

            elif level == "WARN":
                data.warnings.append(WarningEvent(timestamp=timestamp, message=payload))

            elif level == "INFO":
                # Try user-event pattern first
                user_match = _RE_USER.match(payload)
                if user_match:
                    data.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                # Then try API-call pattern
                api_match = _RE_API.match(payload)
                if api_match:
                    data.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            latency_ms=int(api_match.group("ms")),
                        )
                    )

    return data


# ---------------------------------------------------------------------------
# Transform — compute summaries from extracted data
# ---------------------------------------------------------------------------


def transform(data: LogData) -> TransformedData:
    """Derive analysis summaries from raw log events.

    - Counts occurrences of each error message.
    - Computes per-endpoint latency lists for averaging later.
    - Tracks login/logout to determine currently active sessions.

    Args:
        data: Extracted ``LogData``.

    Returns:
        A ``TransformedData`` with error counts, latency map, and
        active-session count.
    """
    # Error counts
    error_counts: Dict[str, int] = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # API latency grouped by endpoint
    api_latency: Dict[str, List[int]] = {}
    for call in data.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.latency_ms)

    # Active sessions: login adds, logout removes
    sessions: Dict[str, str] = {}
    for evt in data.user_events:
        if "logged in" in evt.action:
            sessions[evt.user_id] = evt.timestamp
        elif "logged out" in evt.action and evt.user_id in sessions:
            sessions.pop(evt.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — persist to SQLite and write the HTML report
# ---------------------------------------------------------------------------


def load_to_db(transformed: TransformedData, db_path: str) -> None:
    """Write summarised metrics to the SQLite database.

    Uses parameterised queries throughout — no string interpolation in SQL.

    Args:
        transformed: Computed summaries to persist.
        db_path: Path to the SQLite database file.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in transformed.error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in transformed.api_latency.items():
        avg_ms = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def load_to_report(transformed: TransformedData, report_path: str) -> None:
    """Generate an HTML report from the transformed data.

    The report contains three sections matching the original output:
    error summary, API latency table, and active session count.

    All dynamic values are HTML-escaped to prevent injection.

    Args:
        transformed: Computed summaries to render.
        report_path: Path to write the HTML report to.
    """
    parts: List[str] = []
    parts.append("<html>")
    parts.append("<head><title>System Report</title></head>")
    parts.append("<body>")

    # --- Error Summary ---
    parts.append("<h1>Error Summary</h1>")
    parts.append("<ul>")
    for msg, count in transformed.error_counts.items():
        parts.append(f"<li><b>{escape(msg)}</b>: {count} occurrences</li>")
    parts.append("</ul>")

    # --- API Latency ---
    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in transformed.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        parts.append(f"<tr><td>{escape(endpoint)}</td><td>{avg}</td></tr>")
    parts.append("</table>")

    # --- Active Sessions ---
    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{transformed.active_sessions} user(s) currently active</p>")

    parts.append("</body>")
    parts.append("</html>")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))


def load(transformed: TransformedData, db_path: str, report_path: str) -> None:
    """Persist transformed data to the database and write the HTML report.

    Args:
        transformed: Computed summaries to persist.
        db_path: Path to the SQLite database file.
        report_path: Path to write the HTML report to.
    """
    load_to_db(transformed, db_path)
    load_to_report(transformed, report_path)


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def run_pipeline(
    log_file: str = LOG_FILE,
    db_path: str = DB_PATH,
    report_path: str = REPORT_PATH,
) -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Args:
        log_file: Path to the server log file.
        db_path: Path to the SQLite database.
        report_path: Path for the generated HTML report.
    """
    raw = extract(log_file)
    transformed = transform(raw)
    load(transformed, db_path, report_path)
    print(f"Job finished at {datetime.datetime.now()}")


def _write_sample_log(path: str) -> None:
    """Create a sample log file for demonstration / testing."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines) + "\n")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        _write_sample_log(LOG_FILE)
    run_pipeline()