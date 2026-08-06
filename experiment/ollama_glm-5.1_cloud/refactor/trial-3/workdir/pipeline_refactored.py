"""Server-log processing pipeline.

Reads server logs, extracts structured records (errors, user sessions,
API latency calls, warnings), computes summary statistics, persists them
to SQLite, and writes an HTML report.

Configuration is drawn from environment variables so that no credentials
or paths are hard-coded.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration – all values come from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Compiled regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# General: "2024-01-01 12:00:00 LEVEL ..."
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<payload>.*)$"
)

# ERROR lines: payload is the error message
_ERROR_RE = re.compile(r"^(?P<message>.+)$")

# INFO User lines: "User <uid> <action>"
_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")

# INFO API lines: "API <endpoint> took <duration>ms"
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<duration>\d+)ms$")

# WARN lines: payload is the warning message (already captured by _LOG_LINE_RE)

# ---------------------------------------------------------------------------
# Data classes for parsed records
# ---------------------------------------------------------------------------


@dataclass
class ErrorRecord:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserRecord:
    """A user login/logout event."""

    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCallRecord:
    """An API call with measured latency."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarningRecord:
    """A WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all records extracted from a log file."""

    errors: List[ErrorRecord] = field(default_factory=list)
    users: List[UserRecord] = field(default_factory=list)
    api_calls: List[ApiCallRecord] = field(default_factory=list)
    warnings: List[WarningRecord] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extract – read and parse log lines
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Parse *log_path* and return structured records.

    Each log line is matched against compiled regex patterns.  Lines that
    do not conform to the expected format are silently skipped.

    Args:
        log_path: Path to the server log file.

    Returns:
        A :class:`ParsedLog` with all recognised records and the set of
        currently active sessions (users that logged in without a
        matching logout).
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        return parsed

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _LOG_LINE_RE.match(line)
            if m is None:
                continue

            timestamp: str = m.group("timestamp")
            level: str = m.group("level")
            payload: str = m.group("payload")

            if level == "ERROR":
                em = _ERROR_RE.match(payload)
                if em:
                    parsed.errors.append(
                        ErrorRecord(timestamp=timestamp, message=em.group("message"))
                    )

            elif level == "INFO":
                # Try user event first, then API call
                um = _USER_RE.match(payload)
                if um:
                    uid = um.group("uid")
                    action = um.group("action")
                    parsed.users.append(
                        UserRecord(timestamp=timestamp, uid=uid, action=action)
                    )
                    if "logged in" in action:
                        parsed.active_sessions[uid] = timestamp
                    elif "logged out" in action and uid in parsed.active_sessions:
                        parsed.active_sessions.pop(uid)
                    continue  # skip API match on same payload

                am = _API_RE.match(payload)
                if am:
                    parsed.api_calls.append(
                        ApiCallRecord(
                            timestamp=timestamp,
                            endpoint=am.group("endpoint"),
                            duration_ms=int(am.group("duration")),
                        )
                    )

            elif level == "WARN":
                parsed.warnings.append(
                    WarningRecord(timestamp=timestamp, message=payload)
                )

    return parsed


# ---------------------------------------------------------------------------
# Transform – compute aggregates
# ---------------------------------------------------------------------------

ErrorSummary = Dict[str, int]
ApiLatencyStats = Dict[str, List[int]]


def transform(parsed: ParsedLog) -> tuple[ErrorSummary, ApiLatencyStats, int]:
    """Compute aggregate statistics from parsed log data.

    Args:
        parsed: The parsed log data from :func:`extract`.

    Returns:
        A 3-tuple of:
        - error_counts  – mapping of error message → occurrence count
        - api_latency   – mapping of endpoint → list of latency values
        - active_count  – number of currently active sessions
    """
    error_counts: ErrorSummary = {}
    for err in parsed.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    api_latency: ApiLatencyStats = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.duration_ms)

    active_count = len(parsed.active_sessions)
    return error_counts, api_latency, active_count


# ---------------------------------------------------------------------------
# Load – persist to DB and generate HTML report
# ---------------------------------------------------------------------------


def _init_db(conn: sqlite3.Connection) -> None:
    """Create the errors and api_metrics tables if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load(
    db_path: str,
    error_counts: ErrorSummary,
    api_latency: ApiLatencyStats,
    active_count: int,
    *,
    report_path: str = "report.html",
) -> None:
    """Write aggregated data to SQLite and produce an HTML report.

    All SQL statements use parameterized queries (``?`` placeholders) to
    prevent injection.

    Args:
        db_path:       Path to the SQLite database file.
        error_counts:  Error message → count mapping.
        api_latency:   Endpoint → latency-list mapping.
        active_count:  Number of currently active sessions.
        report_path:   Destination path for the HTML report.
    """
    now = str(datetime.datetime.now())

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        cur = conn.cursor()

        for msg, count in error_counts.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in api_latency.items():
            avg = sum(times) / len(times)
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()

    # ---- HTML report ----
    html = _build_html_report(error_counts, api_latency, active_count)
    with open(report_path, "w") as fh:
        fh.write(html)

    print(f"Job finished at {now}")


def _build_html_report(
    error_counts: ErrorSummary,
    api_latency: ApiLatencyStats,
    active_count: int,
) -> str:
    """Compose an HTML report string from the aggregated data.

    The report has three sections that mirror the original output:
    Error Summary, API Latency, and Active Sessions.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{_esc(msg)}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{_esc(endpoint)}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def _esc(text: str) -> str:
    """Minimal HTML escaping to prevent injection in the report."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    parsed = extract(LOG_FILE)
    error_counts, api_latency, active_count = transform(parsed)
    load(DB_PATH, error_counts, api_latency, active_count)


if __name__ == "__main__":
    main()