"""Refactored server-log pipeline: Extract → Transform → Load.

Reads server logs, aggregates error counts and API latency statistics,
persists results to SQLite, and generates an HTML report.

All configuration is sourced from environment variables with sensible
defaults so the script works out of the box with the sample log.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration — all values from environment variables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables.

    Environment variables and their defaults:
        DB_PATH      – path to the SQLite database      (default: metrics.db)
        LOG_FILE     – path to the server log file       (default: server.log)
        DB_HOST      – database host (informational)     (default: localhost)
        DB_PORT      – database port (informational)     (default: 5432)
        DB_USER      – database user (informational)     (default: admin)
        DB_PASS      – database password (informational) (default: password123)
    """

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables, falling back to defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
        )


# ---------------------------------------------------------------------------
# Parsed log records
# ---------------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """An ERROR-level log entry."""
    timestamp: str
    message: str


@dataclass
class UserRecord:
    """An INFO-level user action (login / logout)."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCallRecord:
    """An INFO-level API call with its latency."""
    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarnRecord:
    """A WARN-level log entry."""
    timestamp: str
    message: str


@dataclass
class LogData:
    """Aggregation of all parsed log entries."""
    errors: list[ErrorRecord] = field(default_factory=list)
    user_events: list[UserRecord] = field(default_factory=list)
    api_calls: list[ApiCallRecord] = field(default_factory=list)
    warnings: list[WarnRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# e.g. "2024-01-01 12:05:00 ERROR Database timeout"
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<payload>.+)$"
)

# e.g. "User 42 logged in"
_USER_RE = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")

# e.g. "API /users/profile took 250ms"  (took-part is optional)
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract — parse the log file
# ---------------------------------------------------------------------------

def extract(log_path: str) -> LogData:
    """Read *log_path* and return structured :class:`LogData`.

    Unrecognised or malformed lines are silently skipped.
    """
    data = LogData()
    path = Path(log_path)

    if not path.exists():
        return data

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            payload = match.group("payload")

            if level == "ERROR":
                data.errors.append(
                    ErrorRecord(timestamp=timestamp, message=payload)
                )

            elif level == "WARN":
                data.warnings.append(
                    WarnRecord(timestamp=timestamp, message=payload)
                )

            elif level == "INFO":
                # Try user-action pattern first
                user_m = _USER_RE.match(payload)
                if user_m:
                    data.user_events.append(
                        UserRecord(
                            timestamp=timestamp,
                            user_id=user_m.group("user_id"),
                            action=user_m.group("action"),
                        )
                    )
                    continue

                # Then try API-call pattern
                api_m = _API_RE.match(payload)
                if api_m:
                    ms_str = api_m.group("ms") or "0"
                    data.api_calls.append(
                        ApiCallRecord(
                            timestamp=timestamp,
                            endpoint=api_m.group("endpoint"),
                            latency_ms=int(ms_str),
                        )
                    )

    return data


# ---------------------------------------------------------------------------
# Transform — compute aggregates
# ---------------------------------------------------------------------------

@dataclass
class ErrorSummary:
    """Count of occurrences for each distinct error message."""
    message: str
    count: int


@dataclass
class ApiLatency:
    """Average latency for a single API endpoint."""
    endpoint: str
    avg_ms: float


@dataclass
class TransformResult:
    """All computed aggregates ready for persistence and reporting."""
    error_summaries: list[ErrorSummary]
    api_latencies: list[ApiLatency]
    active_session_count: int


def transform(data: LogData) -> TransformResult:
    """Aggregate raw :class:`LogData` into reporting-ready summaries.

    Active sessions are users who logged in but have not yet logged out.
    """
    # Error counts
    error_counts: dict[str, int] = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1
    error_summaries = [
        ErrorSummary(message=msg, count=count)
        for msg, count in error_counts.items()
    ]

    # API latency averages
    endpoint_times: dict[str, list[int]] = {}
    for call in data.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.latency_ms)
    api_latencies = [
        ApiLatency(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in endpoint_times.items()
    ]

    # Active sessions (logged in without a matching logged out)
    sessions: dict[str, str] = {}  # user_id -> timestamp
    for evt in data.user_events:
        if "logged in" in evt.action:
            sessions[evt.user_id] = evt.timestamp
        elif "logged out" in evt.action and evt.user_id in sessions:
            sessions.pop(evt.user_id)

    return TransformResult(
        error_summaries=error_summaries,
        api_latencies=api_latencies,
        active_session_count=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — persist to SQLite and write the HTML report
# ---------------------------------------------------------------------------

def load_db(
    config: Config,
    result: TransformResult,
) -> None:
    """Insert aggregated data into the SQLite database at *config.db_path*.

    Uses parameterised queries to prevent SQL injection.
    """
    conn = sqlite3.connect(config.db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for summary in result.error_summaries:
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, summary.message, summary.count),
        )

    for latency in result.api_latencies:
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, latency.endpoint, latency.avg_ms),
        )

    conn.commit()
    conn.close()
    print(
        f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}..."
    )


def load_report(
    result: TransformResult,
    output_path: str = "report.html",
) -> None:
    """Generate an HTML report and write it to *output_path*.

    The report contains:
      • Error summary (message → occurrence count)
      • API latency table (endpoint → average ms)
      • Active session count
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for summary in result.error_summaries:
        lines.append(
            f"<li><b>{escape(summary.message)}</b>: "
            f"{summary.count} occurrences</li>"
        )
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for latency in result.api_latencies:
        lines.append(
            f"<tr><td>{escape(latency.endpoint)}</td>"
            f"<td>{round(latency.avg_ms, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(
        f"<p>{result.active_session_count} user(s) currently active</p>"
    )
    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"Job finished at {datetime.datetime.now()}")


def load(
    config: Config,
    result: TransformResult,
    report_path: str = "report.html",
) -> None:
    """Persist aggregates to the database and write the HTML report."""
    load_db(config, result)
    load_report(result, report_path)


# ---------------------------------------------------------------------------
# Sample log generation (mirrors original __main__ behaviour)
# ---------------------------------------------------------------------------

_SAMPLE_LOG_LINES: list[str] = [
    "2024-01-01 12:00:00 INFO User 42 logged in",
    "2024-01-01 12:05:00 ERROR Database timeout",
    "2024-01-01 12:05:05 ERROR Database timeout",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
    "2024-01-01 12:09:00 WARN Memory usage at 87%",
    "2024-01-01 12:10:00 INFO User 42 logged out",
]


def ensure_sample_log(log_path: str) -> None:
    """Write sample log data if *log_path* does not already exist."""
    path = Path(log_path)
    if path.exists():
        return
    with path.open("w", encoding="utf-8") as fh:
        for line in _SAMPLE_LOG_LINES:
            fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline."""
    config = Config.from_env()
    ensure_sample_log(config.log_file)
    data = extract(config.log_file)
    result = transform(data)
    load(config, result)


if __name__ == "__main__":
    run_pipeline()