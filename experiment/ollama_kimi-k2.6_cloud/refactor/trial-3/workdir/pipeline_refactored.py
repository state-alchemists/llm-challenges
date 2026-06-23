"""Refactored ETL pipeline that processes server logs and generates an HTML report.

This module follows the Extract → Transform → Load pattern:
- **Extract**: parse log lines with regex.
- **Transform**: aggregate error counts, API latency averages, and active sessions.
- **Load**: persist aggregated metrics to SQLite and write ``report.html``.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Regular expressions for log line parsing
# ---------------------------------------------------------------------------

_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "  # timestamp
    r"(\w+) "                                      # level
    r"(.*)$"                                       # remainder
)

_USER_RE = re.compile(
    r"User\s+(\S+)\s+(.*)$"
)

_API_RE = re.compile(
    r"API\s+(\S+)\s+took\s+(\d+)ms$"
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ParsedLogEntry:
    """A single log entry broken into typed fields."""

    timestamp: str
    level: str
    message: str


@dataclass
class ExtractResult:
    """Container for all data harvested from the log file."""

    errors: List[ParsedLogEntry] = field(default_factory=list)
    warnings: List[ParsedLogEntry] = field(default_factory=list)
    api_calls: List[dict] = field(default_factory=list)
    sessions: Dict[str, str] = field(default_factory=dict)


@dataclass
class TransformResult:
    """Aggregated metrics ready for persistence and reporting."""

    error_counts: Dict[str, int] = field(default_factory=dict)
    api_averages: Dict[str, float] = field(default_factory=dict)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build a ``Config`` instance from the process environment.

        Raises:
            KeyError: If a required variable is missing.
        """
        return cls(
            db_path=os.environ["DB_PATH"],
            log_file=os.environ["LOG_FILE"],
            db_host=os.environ["DB_HOST"],
            db_port=int(os.environ["DB_PORT"]),
            db_user=os.environ["DB_USER"],
            db_pass=os.environ["DB_PASS"],
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(log_path: str) -> ExtractResult:
    """Read ``log_path`` and parse each line into structured records.

    Args:
        log_path: Path to the server log file.

    Returns:
        An ``ExtractResult`` holding errors, warnings, API calls, and sessions.
    """
    result = ExtractResult()

    if not os.path.exists(log_path):
        return result

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            match = _LOG_RE.match(line)
            if not match:
                continue

            timestamp, level, remainder = match.groups()
            entry = ParsedLogEntry(
                timestamp=timestamp, level=level, message=remainder
            )

            if level == "ERROR":
                result.errors.append(entry)

            elif level == "WARN":
                result.warnings.append(entry)

            elif level == "INFO":
                if "User" in remainder:
                    user_match = _USER_RE.match(remainder)
                    if user_match:
                        uid, action = user_match.groups()
                        if "logged in" in action:
                            result.sessions[uid] = timestamp
                        elif "logged out" in action and uid in result.sessions:
                            result.sessions.pop(uid)

                elif "API" in remainder:
                    api_match = _API_RE.match(remainder)
                    if api_match:
                        endpoint, duration = api_match.groups()
                        result.api_calls.append(
                            {
                                "timestamp": timestamp,
                                "endpoint": endpoint,
                                "ms": int(duration),
                            }
                        )

    return result


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(extracted: ExtractResult) -> TransformResult:
    """Aggregate extracted records into summary metrics.

    Args:
        extracted: The raw data harvested from the log file.

    Returns:
        A ``TransformResult`` with error counts, API averages, and active sessions.
    """
    error_counts: Dict[str, int] = {}
    for entry in extracted.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in extracted.api_calls:
        endpoint = call["endpoint"]
        endpoint_stats.setdefault(endpoint, []).append(call["ms"])

    api_averages: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_stats.items()
    }

    return TransformResult(
        error_counts=error_counts,
        api_averages=api_averages,
        active_sessions=len(extracted.sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(db_path: str, metrics: TransformResult) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        metrics: Aggregated metrics produced by ``transform``.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    for msg, count in metrics.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in metrics.api_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(metrics: TransformResult, report_path: str = "report.html") -> None:
    """Write an HTML report summarising the transformed metrics.

    Args:
        metrics: Aggregated metrics produced by ``transform``.
        report_path: Destination path for the HTML file.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in metrics.error_counts.items():
        escaped_msg = err_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"<li><b>{escaped_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, avg_ms in metrics.api_averages.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{metrics.active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


def load(db_path: str, metrics: TransformResult) -> None:
    """Load metrics into the database and generate the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        metrics: Aggregated metrics produced by ``transform``.
    """
    load_to_database(db_path, metrics)
    generate_report(metrics)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(config: Config) -> None:
    """Execute the full ETL pipeline.

    Args:
        config: Runtime configuration (paths and credentials).
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    extracted = extract(config.log_file)
    metrics = transform(extracted)
    load(config.db_path, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


def _ensure_sample_log(log_path: str) -> None:
    """Create a sample ``server.log`` if none exists so the demo runs out-of-the-box."""
    if os.path.exists(log_path):
        return
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


if __name__ == "__main__":
    cfg = Config.from_env()
    _ensure_sample_log(cfg.log_file)
    run_pipeline(cfg)
