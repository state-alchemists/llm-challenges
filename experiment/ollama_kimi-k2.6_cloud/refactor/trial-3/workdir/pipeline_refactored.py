"""Refactored log processing pipeline with ETL structure.

Reads server logs, aggregates metrics, persists them to SQLite,
and generates an HTML report. Configuration is externalised to
environment variables; SQL queries are parameterised; and log
parsing uses regular expressions for robustness.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: str

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config instance from the process environment.

        Falls back to the legacy hard-coded defaults so existing
        deployments continue to work.
        """
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
            report_path=os.getenv("REPORT_PATH", "report.html"),
        )


# ---------------------------------------------------------------------------
# Regular-expression patterns for log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR|INFO|WARN)(?:\s+(.*))?$"
)
_USER_ACTION_RE = re.compile(r"^User\s+(\d+)\s+(.+)$")
_API_CALL_RE = re.compile(r"^API\s+(\S+)\s+took\s+(\d+)ms$")


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorEvent:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass(frozen=True)
class ApiEvent:
    """An INFO-level API latency log entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True)
class UserEvent:
    """An INFO-level user session log entry."""

    timestamp: str
    user_id: str
    action: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_sample_log(log_path: str) -> None:
    """Seed a sample log file if one does not yet exist on disk."""
    if os.path.exists(log_path):
        return
    with open(log_path, "w") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(log_path: str) -> Tuple[List[ErrorEvent], List[ApiEvent], List[UserEvent]]:
    """Parse *log_path* into structured events.

    Args:
        log_path: Absolute or relative path to the server log file.

    Returns:
        Three-tuple of ``(errors, api_calls, user_events)``.
    """
    errors: List[ErrorEvent] = []
    api_calls: List[ApiEvent] = []
    user_events: List[UserEvent] = []

    with open(log_path, "r") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group(1)
            level = match.group(2)
            payload = match.group(3) or ""

            if level == "ERROR":
                errors.append(ErrorEvent(timestamp=timestamp, message=payload.strip()))
                continue

            if level == "WARN":
                # Preserved from the original: WARN lines are parsed but do
                # not feed into any downstream metric or report.
                continue

            if level != "INFO":
                continue

            user_match = _USER_ACTION_RE.match(payload)
            if user_match:
                user_events.append(
                    UserEvent(
                        timestamp=timestamp,
                        user_id=user_match.group(1),
                        action=user_match.group(2).strip(),
                    )
                )
                continue

            api_match = _API_CALL_RE.match(payload)
            if api_match:
                api_calls.append(
                    ApiEvent(
                        timestamp=timestamp,
                        endpoint=api_match.group(1),
                        duration_ms=int(api_match.group(2)),
                    )
                )

    return errors, api_calls, user_events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(
    errors: List[ErrorEvent],
    api_calls: List[ApiEvent],
    user_events: List[UserEvent],
) -> Tuple[Dict[str, int], Dict[str, float], int]:
    """Aggregate raw events into report-ready metrics.

    Args:
        errors: Parsed ERROR events.
        api_calls: Parsed API latency events.
        user_events: Parsed user session events.

    Returns:
        Three-tuple of ``(error_counts, api_averages, active_sessions)``.
    """
    error_counts: Dict[str, int] = {}
    for ev in errors:
        error_counts[ev.message] = error_counts.get(ev.message, 0) + 1

    endpoint_times: Dict[str, List[int]] = defaultdict(list)
    for ev in api_calls:
        endpoint_times[ev.endpoint].append(ev.duration_ms)

    api_averages: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_times.items()
    }

    sessions: Dict[str, str] = {}
    for ev in user_events:
        if "logged in" in ev.action:
            sessions[ev.user_id] = ev.timestamp
        elif "logged out" in ev.action and ev.user_id in sessions:
            del sessions[ev.user_id]

    return error_counts, api_averages, len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load(
    db_path: str,
    report_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions: int,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Persist metrics to the database and write the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        report_path: Destination path for the generated HTML report.
        error_counts: Aggregated error frequencies.
        api_averages: Aggregated API latencies (average ms per endpoint).
        active_sessions: Number of users still logged in.
        db_host: Display-only database host name.
        db_port: Display-only database port.
        db_user: Display-only database username.
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg_ms in api_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()
    conn.close()

    html = _render_html(error_counts, api_averages, active_sessions)
    with open(report_path, "w") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


def _render_html(
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions: int,
) -> str:
    """Assemble the system report as an HTML string.

    The layout mirrors the original report exactly.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in api_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Orchestrate the Extract → Transform → Load pipeline."""
    config = Config.from_env()
    create_sample_log(config.log_file)

    errors, api_calls, user_events = extract(config.log_file)
    error_counts, api_averages, active_sessions = transform(
        errors, api_calls, user_events
    )
    load(
        db_path=config.db_path,
        report_path=config.report_path,
        error_counts=error_counts,
        api_averages=api_averages,
        active_sessions=active_sessions,
        db_host=config.db_host,
        db_port=config.db_port,
        db_user=config.db_user,
    )


if __name__ == "__main__":
    main()
