"""Server-log ETL pipeline: extract → transform → load into SQLite, then generate an HTML report.

All configuration is read from environment variables with sensible defaults.
SQL uses parameterized queries to prevent injection. Log parsing uses regex.
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
# Configuration — all values come from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# Expected log format: "2024-01-01 12:00:00 LEVEL rest-of-message"
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<rest>.*)$"
)

# INFO lines about users: "User 42 logged in" / "User 42 logged out"
_USER_RE = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$"
)

# INFO lines about API calls: "API /users/profile took 250ms"
_API_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms$"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ErrorEvent:
    """An ERROR-level log entry."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """An INFO-level user login/logout event."""
    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCall:
    """An INFO-level API latency measurement."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class ParsedLog:
    """Container for all data extracted from the log file."""
    errors: List[ErrorEvent] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EXTRACT — read and parse the log file
# ---------------------------------------------------------------------------

def parse_log_line(line: str) -> Optional[tuple[str, str, str]]:
    """Match a single log line against the timestamp/level/rest pattern.

    Returns a (timestamp, level, rest) tuple, or *None* if the line
    does not conform to the expected format.
    """
    match = _LOG_LINE_RE.match(line.strip())
    if not match:
        return None
    return match.group("timestamp"), match.group("level"), match.group("rest")


def extract(log_path: str) -> ParsedLog:
    """Read *log_path* and return structured :class:`ParsedLog` data.

    Unrecognised lines are silently skipped.
    """
    parsed = ParsedLog()
    path = Path(log_path)

    if not path.exists():
        return parsed

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            result = parse_log_line(raw_line)
            if result is None:
                continue

            timestamp, level, rest = result

            if level == "ERROR":
                parsed.errors.append(ErrorEvent(timestamp=timestamp, message=rest))

            elif level == "WARN":
                parsed.warnings.append(rest)

            elif level == "INFO":
                # Try user event first, then API call
                user_match = _USER_RE.match(rest)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            uid=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    parsed.api_calls.append(
                        ApiCall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            latency_ms=int(api_match.group("ms")),
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# TRANSFORM — compute aggregates
# ---------------------------------------------------------------------------

@dataclass
class ErrorSummary:
    """Count of occurrences keyed by error message."""
    message: str
    count: int


@dataclass
class ApiLatency:
    """Average latency for a single endpoint."""
    endpoint: str
    avg_ms: float


@dataclass
class TransformResult:
    """All aggregates needed for the report and DB."""
    error_summaries: List[ErrorSummary] = field(default_factory=list)
    api_latencies: List[ApiLatency] = field(default_factory=list)
    active_sessions: int = 0


def transform(parsed: ParsedLog) -> TransformResult:
    """Derive aggregates from raw parsed log data.

    * Error messages → per-message occurrence counts.
    * API calls → per-endpoint average latency.
    * User events → current active-session count (logins minus logouts).
    """
    # Error summary
    error_counts: Dict[str, int] = {}
    for err in parsed.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1
    error_summaries = [
        ErrorSummary(message=msg, count=count)
        for msg, count in error_counts.items()
    ]

    # API latency averages
    endpoint_times: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.latency_ms)
    api_latencies = [
        ApiLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in endpoint_times.items()
    ]

    # Active sessions: users who logged in without a matching logout
    sessions: Dict[str, str] = {}
    for evt in parsed.user_events:
        if "logged in" in evt.action:
            sessions[evt.uid] = evt.timestamp
        elif "logged out" in evt.action and evt.uid in sessions:
            sessions.pop(evt.uid, None)

    return TransformResult(
        error_summaries=error_summaries,
        api_latencies=api_latencies,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# LOAD — persist to SQLite
# ---------------------------------------------------------------------------

def _init_schema(cursor: sqlite3.Cursor) -> None:
    """Create tables if they do not already exist."""
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load(db_path: str, result: TransformResult) -> None:
    """Persist aggregated data into the SQLite database at *db_path*.

    Uses parameterised queries exclusively — no string interpolation.
    """
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        _init_schema(cursor)

        for summary in result.error_summaries:
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, summary.message, summary.count),
            )

        for latency in result.api_latencies:
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, latency.endpoint, latency.avg_ms),
            )

        conn.commit()
    finally:
        conn.close()

    print(f"Connected to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# REPORT — generate the HTML report
# ---------------------------------------------------------------------------

def generate_report(result: TransformResult, output_path: str = "report.html") -> None:
    """Write an HTML report to *output_path* containing the error summary,
    API latency table, and active session count.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for summary in result.error_summaries:
        lines.append(
            f"<li><b>{summary.message}</b>: {summary.count} occurrences</li>"
        )

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for latency in result.api_latencies:
        lines.append(
            f"<tr><td>{latency.endpoint}</td>"
            f"<td>{round(latency.avg_ms, 1)}</td></tr>"
        )

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{result.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def create_sample_log(log_path: str) -> None:
    """Write a small sample log file so the pipeline has something to process."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    Path(log_path).write_text("\n".join(sample_lines) + "\n", encoding="utf-8")


def run_pipeline() -> None:
    """Execute the full ETL pipeline: extract → transform → load → report."""
    if not Path(LOG_FILE).exists():
        create_sample_log(LOG_FILE)

    parsed = extract(LOG_FILE)
    result = transform(parsed)
    load(DB_PATH, result)
    generate_report(result)


if __name__ == "__main__":
    run_pipeline()