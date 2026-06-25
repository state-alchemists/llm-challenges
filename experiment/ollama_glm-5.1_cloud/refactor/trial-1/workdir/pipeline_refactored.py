"""Server-log ETL pipeline: extract, transform, and load metrics into a report.

Reads server logs, aggregates errors/API latencies/sessions, persists to
SQLite, and writes an HTML report. All configuration is sourced from
environment variables; no credentials are hardcoded outside env-var defaults.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """An aggregated error message and its occurrence count."""
    message: str
    count: int


@dataclass
class ApiCall:
    """A single API call record with endpoint and latency."""
    endpoint: str
    latency_ms: int


@dataclass
class ParsedLog:
    """All data extracted from a server log file."""
    errors: List[ErrorEntry] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<payload>.*)$"
)

_USER_ACTION_RE = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$"
)

_API_CALL_RE = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_log_data(log_path: str) -> ParsedLog:
    """Parse server log lines into structured records.

    Reads *log_path* line-by-line and classifies each entry as an error,
    user session event, API call, or warning using regex patterns.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ParsedLog containing aggregated errors, API calls, active
        sessions, and warnings.
    """
    result = ParsedLog()
    sessions: Dict[str, str] = {}
    error_counts: Dict[str, int] = {}

    if not os.path.exists(log_path):
        return result

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = _LOG_LINE_RE.match(line.strip())
            if not match:
                continue

            level = match.group("level")
            payload = match.group("payload")

            if level == "ERROR":
                msg = payload.strip()
                error_counts[msg] = error_counts.get(msg, 0) + 1

            elif level == "INFO":
                user_m = _USER_ACTION_RE.match(payload)
                if user_m:
                    uid = user_m.group("uid")
                    action = user_m.group("action").strip()
                    if "logged in" in action:
                        sessions[uid] = match.group("timestamp")
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid, None)
                    continue

                api_m = _API_CALL_RE.match(payload)
                if api_m:
                    endpoint = api_m.group("endpoint")
                    ms = int(api_m.group("ms") or 0)
                    result.api_calls.append(ApiCall(endpoint=endpoint, latency_ms=ms))
                    continue

            elif level == "WARN":
                result.warnings.append(payload.strip())

    for msg, count in error_counts.items():
        result.errors.append(ErrorEntry(message=msg, count=count))
    result.active_sessions = sessions

    return result


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_log_entries(parsed: ParsedLog) -> Dict[str, Dict[str, float]]:
    """Compute summary statistics from parsed log data.

    Args:
        parsed: Extracted log records.

    Returns:
        A dict with keys ``"errors"`` (mapping error messages to counts)
        and ``"api_latency"`` (mapping endpoints to average latency in ms).
    """
    error_summary: Dict[str, float] = {
        err.message: float(err.count) for err in parsed.errors
    }

    latency_by_endpoint: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        latency_by_endpoint.setdefault(call.endpoint, []).append(call.latency_ms)

    api_latency: Dict[str, float] = {}
    for endpoint, times in latency_by_endpoint.items():
        api_latency[endpoint] = sum(times) / len(times)

    return {
        "errors": error_summary,
        "api_latency": api_latency,
    }


# ---------------------------------------------------------------------------
# Load / Report
# ---------------------------------------------------------------------------

def load_report(
    parsed: ParsedLog,
    summaries: Dict[str, Dict[str, float]],
    db_path: str,
) -> None:
    """Persist metrics to SQLite and write the HTML report.

    Inserts aggregated error counts and API latency averages into the
    database using parameterized queries, then generates ``report.html``.

    Args:
        parsed: Extracted log records (used for session count).
        summaries: Transformed statistics from :func:`transform_log_entries`.
        db_path: Path to the SQLite database file.
    """
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in summaries["errors"].items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, int(count)),
        )

    for endpoint, avg_ms in summaries["api_latency"].items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()

    _write_html_report(parsed, summaries)


def _write_html_report(
    parsed: ParsedLog,
    summaries: Dict[str, Dict[str, float]],
) -> None:
    """Render and write the HTML report to ``report.html``.

    Args:
        parsed: Extracted log records (used for session count).
        summaries: Transformed statistics from :func:`transform_log_entries`.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in summaries["errors"].items():
        lines.append(f"<li><b>{msg}</b>: {int(count)} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, avg_ms in summaries["api_latency"].items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(parsed.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline: extract, transform, load."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed = extract_log_data(LOG_FILE)
    summaries = transform_log_entries(parsed)
    load_report(parsed, summaries, DB_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()