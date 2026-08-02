"""ETL pipeline that processes server logs and generates an HTML report.

Reads configuration from environment variables, parses log lines with
regex, stores aggregated metrics in SQLite via parameterized queries,
and writes a report to report.html.

Environment variables:
    LOG_FILE     – Path to the server log file (default: server.log)
    DB_PATH      – Path to the SQLite database (default: metrics.db)
    DB_USER      – Database username (used for logging only; default: admin)
    DB_PASS      – Database password (used for logging only; default: password123)
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

LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")

# These two are kept for backward-compatible log output only; SQLite has
# its own auth model and does not use them for connections.
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    """A parsed server log line."""
    timestamp: str
    level: str
    message: str


@dataclass
class ApiCall:
    """An API call recorded in a log line."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class SessionEvent:
    """A user login/logout event."""
    timestamp: str
    user_id: str
    action: str  # "logged in" | "logged out"


@dataclass
class ParsedLogs:
    """Aggregated result of parsing all log lines."""
    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    session_events: List[SessionEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Log-line regex patterns
# ---------------------------------------------------------------------------

# Generic: "2024-01-01 12:05:00 LEVEL rest-of-line"
_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<payload>.*)$"
)

# User event: "User <id> <action>"
_RE_USER = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# API call: "API <endpoint> took <n>ms"  (latency part is optional)
_RE_API = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<latency>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract – read and parse log lines
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> Optional[tuple[str, str, str]]:
    """Return (timestamp, level, payload) or *None* if *line* doesn't match."""
    m = _RE_LOG_LINE.match(line)
    if not m:
        return None
    return m.group("timestamp"), m.group("level"), m.group("payload")


def classify_entry(
    timestamp: str,
    level: str,
    payload: str,
) -> List[LogEntry | ApiCall | SessionEvent]:
    """Classify a parsed log line into structured records.

    A single line may produce one record (or none if unrecognised).
    """
    records: List[LogEntry | ApiCall | SessionEvent] = []

    if level == "ERROR":
        records.append(LogEntry(timestamp=timestamp, level="ERROR", message=payload.strip()))

    elif level == "WARN":
        records.append(LogEntry(timestamp=timestamp, level="WARN", message=payload.strip()))

    elif level == "INFO":
        # Try user event first
        u = _RE_USER.match(payload)
        if u:
            records.append(SessionEvent(
                timestamp=timestamp,
                user_id=u.group("user_id"),
                action=u.group("action").strip(),
            ))
            return records

        # Then API call
        a = _RE_API.match(payload)
        if a:
            latency = int(a.group("latency")) if a.group("latency") else 0
            records.append(ApiCall(
                timestamp=timestamp,
                endpoint=a.group("endpoint"),
                latency_ms=latency,
            ))

    return records


def extract(log_path: str) -> ParsedLogs:
    """Read *log_path* and return parsed, classified log data."""
    logs = ParsedLogs()

    path = Path(log_path)
    if not path.exists():
        return logs

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            parsed = parse_log_line(line)
            if parsed is None:
                continue
            timestamp, level, payload = parsed

            for record in classify_entry(timestamp, level, payload):
                if isinstance(record, LogEntry):
                    if record.level == "ERROR":
                        logs.errors.append(record)
                    else:
                        logs.warnings.append(record)
                elif isinstance(record, SessionEvent):
                    logs.session_events.append(record)
                elif isinstance(record, ApiCall):
                    logs.api_calls.append(record)

    return logs


# ---------------------------------------------------------------------------
# Transform – aggregate raw records into report-ready structures
# ---------------------------------------------------------------------------

def compute_error_summary(errors: List[LogEntry]) -> Dict[str, int]:
    """Return a mapping of error message → occurrence count."""
    summary: Dict[str, int] = {}
    for entry in errors:
        summary[entry.message] = summary.get(entry.message, 0) + 1
    return summary


def compute_api_latency(api_calls: List[ApiCall]) -> Dict[str, List[int]]:
    """Return a mapping of endpoint → list of latency measurements."""
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.latency_ms)
    return stats


def compute_active_sessions(events: List[SessionEvent]) -> Dict[str, str]:
    """Return mapping of user_id → login_timestamp for currently active sessions."""
    sessions: Dict[str, str] = {}
    for event in events:
        if event.action == "logged in":
            sessions[event.user_id] = event.timestamp
        elif event.action == "logged out" and event.user_id in sessions:
            sessions.pop(event.user_id)
    return sessions


def transform(logs: ParsedLogs) -> tuple[
    Dict[str, int],
    Dict[str, List[int]],
    Dict[str, str],
]:
    """Aggregate parsed logs into error summary, API latency, and active sessions."""
    return (
        compute_error_summary(logs.errors),
        compute_api_latency(logs.api_calls),
        compute_active_sessions(logs.session_events),
    )


# ---------------------------------------------------------------------------
# Load – persist to database and write HTML report
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure tables exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def load_to_db(
    conn: sqlite3.Connection,
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
) -> None:
    """Insert aggregated metrics into the database using parameterized queries."""
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()

    for msg, count in error_summary.items():
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


def render_html(
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> str:
    """Produce the same HTML report the original script generated."""
    lines: List[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")

    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def write_report(html: str, output_path: str = "report.html") -> None:
    """Write *html* to *output_path*."""
    Path(output_path).write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> None:
    """Full ETL pipeline: extract logs → transform → load to DB + report."""
    print(f"Connecting to {DB_USER}@{DB_PATH}...")

    logs = extract(LOG_FILE)

    error_summary, api_latency, active_sessions = transform(logs)

    conn = init_db(DB_PATH)
    load_to_db(conn, error_summary, api_latency)
    conn.close()

    html = render_html(error_summary, api_latency, active_sessions)
    write_report(html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a sample log file when the configured one is missing, so the
    # script can be run out of the box (mirrors original behaviour).
    if not os.path.exists(LOG_FILE):
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )
    run()