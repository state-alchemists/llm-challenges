"""
Pipeline: Parse server logs → SQLite → HTML report.

ETL stages:
    Extract  — read and parse log lines into structured records
    Transform — aggregate errors and API latency metrics
    Load     — persist to SQLite and render report.html
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

ERROR_RECORD_RE = re.compile(r"(?P<timestamp>\S+ \S+) ERROR (?P<message>.+)")
USER_RECORD_RE = re.compile(
    r"(?P<timestamp>\S+ \S+) INFO User (?P<uid>\S+) (?P<action>.+)"
)
API_RECORD_RE = re.compile(
    r"(?P<timestamp>\S+ \S+) INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms"
)
WARN_RECORD_RE = re.compile(r"(?P<timestamp>\S+ \S+) WARN (?P<message>.+)")


@dataclass
class ErrorRecord:
    timestamp: str
    message: str


@dataclass
class UserRecord:
    timestamp: str
    uid: str
    action: str


@dataclass
class ApiCallRecord:
    timestamp: str
    endpoint: str
    ms: int


@dataclass
class ParseResult:
    errors: list[ErrorRecord] = field(default_factory=list)
    users: list[UserRecord] = field(default_factory=list)
    api_calls: list[ApiCallRecord] = field(default_factory=list)


@dataclass
class AggregatedMetrics:
    error_counts: dict[str, int] = field(default_factory=dict)
    active_sessions: int = 0
    endpoint_avg_ms: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EXTRACT — log parsing
# ---------------------------------------------------------------------------


def parse_log_file(path: str) -> ParseResult:
    """
    Read *path* line-by-line and return structured records.

    Each log line is matched against four regex patterns. Unmatched lines are
    silently skipped.
    """
    result = ParseResult()
    if not Path(path).is_file():
        return result

    with open(path, "r") as fh:
        for line in fh:
            if m := ERROR_RECORD_RE.match(line):
                result.errors.append(
                    ErrorRecord(timestamp=m["timestamp"], message=m["message"])
                )
            elif m := USER_RECORD_RE.match(line):
                result.users.append(
                    UserRecord(timestamp=m["timestamp"], uid=m["uid"], action=m["action"])
                )
            elif m := API_RECORD_RE.match(line):
                result.api_calls.append(
                    ApiCallRecord(
                        timestamp=m["timestamp"],
                        endpoint=m["endpoint"],
                        ms=int(m["ms"]),
                    )
                )
            elif m := WARN_RECORD_RE.match(line):
                # WARN lines are collected as errors for reporting purposes
                result.errors.append(
                    ErrorRecord(timestamp=m["timestamp"], message=m["message"])
                )
    return result


# ---------------------------------------------------------------------------
# TRANSFORM — aggregation
# ---------------------------------------------------------------------------


def aggregate_metrics(data: ParseResult) -> AggregatedMetrics:
    """
    Collapse raw records into the summary structures needed for the report.

    - error_counts: message → occurrence count
    - active_sessions: users who logged in but not out
    - endpoint_avg_ms: endpoint → mean latency
    """
    metrics = AggregatedMetrics()

    # Count identical error messages
    for rec in data.errors:
        metrics.error_counts[rec.message] = (
            metrics.error_counts.get(rec.message, 0) + 1
        )

    # Track active sessions (logged in but not yet out)
    sessions: dict[str, str] = {}
    for rec in data.users:
        if "logged in" in rec.action:
            sessions[rec.uid] = rec.timestamp
        elif "logged out" in rec.action:
            sessions.pop(rec.uid, None)
    metrics.active_sessions = len(sessions)

    # Per-endpoint average latency
    endpoint_samples: dict[str, list[int]] = {}
    for rec in data.api_calls:
        endpoint_samples.setdefault(rec.endpoint, []).append(rec.ms)
    metrics.endpoint_avg_ms = {
        ep: sum(samples) / len(samples) for ep, samples in endpoint_samples.items()
    }

    return metrics


# ---------------------------------------------------------------------------
# LOAD — persistence and report generation
# ------------------------------------------------------------------------


def load_metrics(db_path: str, metrics: AggregatedMetrics) -> None:
    """
    Persist *metrics* into a SQLite database at *db_path* using parameterised
    queries. Creates the tables if they do not exist.
    """
    conn = sqlite3.connect(db_path)
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
    for msg, count in metrics.error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg_ms in metrics.endpoint_avg_ms.items():
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()
    conn.close()


def render_html_report(metrics: AggregatedMetrics, output_path: str) -> None:
    """
    Write *metrics* to *output_path* as a self-contained HTML document.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in metrics.error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>",
                  "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])
    for ep, avg_ms in metrics.endpoint_avg_ms.items():
        lines.append(
            f"<tr><td>{ep}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    lines.extend(["</table>", "<h2>Active Sessions</h2>",
                  f"<p>{metrics.active_sessions} user(s) currently active</p>",
                  "</body></html>"])

    Path(output_path).write_text("".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full ETL pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    raw = parse_log_file(LOG_FILE)
    metrics = aggregate_metrics(raw)
    load_metrics(DB_PATH, metrics)
    render_html_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")


# ---------------------------------------------------------------------------
# Bootstrap — create a minimal sample log when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not Path(LOG_FILE).is_file():
        sample = (
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        Path(LOG_FILE).write_text(sample)

    run_pipeline()
