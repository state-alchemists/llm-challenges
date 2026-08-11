"""Server-log processing pipeline.

Extracts structured data from server logs, transforms it into aggregated
metrics, and loads the results into a SQLite database plus an HTML report.

Configuration is read from environment variables with sensible defaults:
    LOG_FILE   – Path to the server log   (default: server.log)
    DB_PATH    – Path to the SQLite DB    (default: metrics.db)
    DB_HOST    – Database host            (default: localhost)
    DB_PORT    – Database port            (default: 5432)
    DB_USER    – Database user            (default: admin)
    DB_PASS    – Database password        (default: password123)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str = os.getenv("DB_PATH", "metrics.db")
    log_file: str = os.getenv("LOG_FILE", "server.log")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_user: str = os.getenv("DB_USER", "admin")
    db_pass: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A parsed user login / logout log line."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class APICall:
    """A parsed API latency log line."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class WarnEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


@dataclass
class ParsedLog:
    """Container for all parsed log entries."""

    errors: List[ErrorEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[APICall] = field(default_factory=list)
    warnings: List[WarnEntry] = field(default_factory=list)


@dataclass
class ErrorSummary:
    """Aggregated error counts keyed by message."""

    counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class APILatencyStats:
    """Per-endpoint latency statistics."""

    avg_ms: Dict[str, float] = field(default_factory=dict)


@dataclass
class TransformedData:
    """Result of the transform step."""

    error_summary: ErrorSummary
    api_latency: APILatencyStats
    active_sessions: int


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

# General log line: "2024-01-01 12:05:00 ERROR Database timeout"
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<rest>.*)$"
)

# User event: "User 42 logged in" or "User 42 logged out"
_USER_EVENT_RE = re.compile(
    r"^User\s+(?P<user_id>\S+)\s+(?P<action>.*)$"
)

# API call: "API /users/profile took 250ms"
_API_CALL_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<latency>\d+)ms$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(log_file: str) -> ParsedLog:
    """Parse every line in *log_file* into structured entries.

    Lines that do not match any known pattern are silently skipped.

    Args:
        log_file: Path to the server log file.

    Returns:
        A :class:`ParsedLog` containing all recognised entries.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_file):
        return parsed

    with open(log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                parsed.errors.append(
                    ErrorEntry(timestamp=timestamp, message=rest)
                )

            elif level == "WARN":
                parsed.warnings.append(
                    WarnEntry(timestamp=timestamp, message=rest)
                )

            elif level == "INFO":
                user_match = _USER_EVENT_RE.match(rest)
                if user_match:
                    parsed.user_events.append(
                        UserEvent(
                            timestamp=timestamp,
                            user_id=user_match.group("user_id"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_CALL_RE.match(rest)
                if api_match:
                    parsed.api_calls.append(
                        APICall(
                            timestamp=timestamp,
                            endpoint=api_match.group("endpoint"),
                            latency_ms=int(api_match.group("latency")),
                        )
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(parsed: ParsedLog) -> TransformedData:
    """Aggregate raw parsed data into report-ready summaries.

    Args:
        parsed: The extracted log data.

    Returns:
        Aggregated error counts, API latency averages, and active session
        count.
    """
    # Error summary
    error_counts: Dict[str, int] = {}
    for err in parsed.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # API latency averages
    endpoint_latencies: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        endpoint_latencies.setdefault(call.endpoint, []).append(call.latency_ms)

    avg_ms: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_latencies.items()
    }

    # Active sessions (logged in but not yet logged out)
    sessions: Dict[str, str] = {}
    for event in parsed.user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            del sessions[event.user_id]

    return TransformedData(
        error_summary=ErrorSummary(counts=error_counts),
        api_latency=APILatencyStats(avg_ms=avg_ms),
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    """Create the required tables if they do not already exist."""
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def load(config: Config, data: TransformedData) -> None:
    """Persist aggregated data to the database and write the HTML report.

    All database writes use parameterised queries to prevent SQL injection.

    Args:
        config: Runtime configuration (paths, credentials).
        data: The transformed / aggregated data to persist.
    """
    now = str(datetime.datetime.now())

    # --- Database ---
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    _init_db(conn)
    cursor = conn.cursor()

    for msg, count in data.error_summary.counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in data.api_latency.avg_ms.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    # --- HTML report ---
    report = _build_html_report(data)
    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"Job finished at {now}")


def _build_html_report(data: TransformedData) -> str:
    """Render the aggregated data into an HTML report string.

    Args:
        data: The transformed data to render.

    Returns:
        A complete HTML document as a string.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_summary.counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, avg in data.api_latency.avg_ms.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{data.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sample data generator (mirrors original __main__ block)
# ---------------------------------------------------------------------------

def _ensure_sample_log(log_file: str) -> None:
    """Write a small sample log when the file does not already exist."""
    if os.path.exists(log_file):
        return
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(log_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sample_lines) + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    config = Config()
    _ensure_sample_log(config.log_file)
    parsed = extract(config.log_file)
    data = transform(parsed)
    load(config, data)


if __name__ == "__main__":
    main()