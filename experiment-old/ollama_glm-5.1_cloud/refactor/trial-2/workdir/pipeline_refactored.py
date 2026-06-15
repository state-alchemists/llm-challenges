"""Pipeline for processing server logs and generating an HTML report.

Refactored from the original monolithic script to follow Extract → Transform → Load
with proper env-var configuration, parameterized SQL, regex-based parsing, and
type-annotated functions with docstrings.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Counter


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Config:
    """All runtime configuration sourced from environment variables."""

    db_path: str
    log_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read configuration from environment variables with sensible defaults."""
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=Path(os.getenv("LOG_FILE", "server.log")),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """A parsed ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A parsed user login/logout log entry."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A parsed API call log entry with latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class WarnEvent:
    """A parsed WARN-level log entry."""

    timestamp: str
    message: str


@dataclass
class LogData:
    """Aggregated results from log extraction."""

    errors: list[ErrorEvent] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    warnings: list[WarnEvent] = field(default_factory=list)


@dataclass
class ErrorSummary:
    """Count of each distinct error message."""

    counts: Counter[str] = field(default_factory=Counter)


@dataclass
class ApiLatency:
    """Average latency per endpoint."""

    averages: dict[str, float] = field(default_factory=dict)


@dataclass
class SessionTracker:
    """Active session count derived from login/logout events."""

    active_count: int = 0


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<payload>.*)$"
)

_USER_PATTERN = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")
_API_PATTERN = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_log_entries(log_path: Path) -> LogData:
    """Parse the server log file into structured records.

    Uses regex patterns to robustly split each line into timestamp,
    level, and payload, then dispatches to level-specific parsers.

    Args:
        log_path: Path to the server log file.

    Returns:
        A `LogData` containing all parsed error, user, API, and warning events.
    """
    data = LogData()

    if not log_path.exists():
        return data

    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_PATTERN.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            payload = match.group("payload")

            if level == "ERROR":
                data.errors.append(ErrorEvent(timestamp=timestamp, message=payload.strip()))

            elif level == "INFO":
                if payload.startswith("User "):
                    m = _USER_PATTERN.match(payload)
                    if m:
                        data.user_events.append(
                            UserEvent(
                                timestamp=timestamp,
                                user_id=m.group("uid"),
                                action=m.group("action"),
                            )
                        )
                elif payload.startswith("API "):
                    m = _API_PATTERN.match(payload)
                    if m:
                        data.api_calls.append(
                            ApiCall(
                                timestamp=timestamp,
                                endpoint=m.group("endpoint"),
                                latency_ms=int(m.group("ms") or 0),
                            )
                        )

            elif level == "WARN":
                data.warnings.append(
                    WarnEvent(timestamp=timestamp, message=payload.strip())
                )

    return data


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_errors(errors: list[ErrorEvent]) -> ErrorSummary:
    """Count occurrences of each distinct error message.

    Args:
        errors: Parsed error events from log extraction.

    Returns:
        An `ErrorSummary` mapping error messages to their occurrence counts.
    """
    summary = ErrorSummary()
    for err in errors:
        summary.counts[err.message] += 1
    return summary


def transform_api_latency(api_calls: list[ApiCall]) -> ApiLatency:
    """Compute average latency per API endpoint.

    Args:
        api_calls: Parsed API call events from log extraction.

    Returns:
        An `ApiLatency` mapping each endpoint to its mean latency in ms.
    """
    buckets: dict[str, list[int]] = {}
    for call in api_calls:
        buckets.setdefault(call.endpoint, []).append(call.latency_ms)

    averages: dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in buckets.items()
    }
    return ApiLatency(averages=averages)


def transform_sessions(user_events: list[UserEvent]) -> SessionTracker:
    """Determine how many user sessions are currently active.

    A session is active if the user has logged in but not yet logged out.

    Args:
        user_events: Parsed user login/logout events.

    Returns:
        A `SessionTracker` with the count of currently active sessions.
    """
    active: set[str] = set()
    for event in user_events:
        if "logged in" in event.action:
            active.add(event.user_id)
        elif "logged out" in event.action:
            active.discard(event.user_id)
    return SessionTracker(active_count=len(active))


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(
    config: Config,
    error_summary: ErrorSummary,
    api_latency: ApiLatency,
) -> None:
    """Persist aggregated metrics to the SQLite database.

    Uses parameterized queries exclusively to prevent SQL injection.

    Args:
        config: Runtime configuration (provides database path).
        error_summary: Aggregated error counts to persist.
        api_latency: Aggregated API latency averages to persist.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = sqlite3.connect(config.db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in error_summary.counts.items():
            cur.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg in api_latency.averages.items():
            cur.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_report(
    report_path: Path,
    error_summary: ErrorSummary,
    api_latency: ApiLatency,
    sessions: SessionTracker,
) -> None:
    """Generate an HTML report from the aggregated metrics.

    Args:
        report_path: Output path for the HTML report file.
        error_summary: Aggregated error counts for the summary section.
        api_latency: Per-endpoint latency averages for the latency table.
        sessions: Active session tracker for the sessions section.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for msg, count in error_summary.counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in api_latency.averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{sessions.active_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with report_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Main entry point: extract log data, transform into metrics, load to DB and report."""
    config = load_config()

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    # Extract
    log_data = extract_log_entries(config.log_file)

    # Transform
    error_summary = transform_errors(log_data.errors)
    api_latency = transform_api_latency(log_data.api_calls)
    sessions = transform_sessions(log_data.user_events)

    # Load
    load_to_database(config, error_summary, api_latency)
    report_path = config.log_file.parent / "report.html"
    load_report(report_path, error_summary, api_latency, sessions)

    print(f"Job finished at {datetime.datetime.now(datetime.timezone.utc)}")


if __name__ == "__main__":
    run_pipeline()