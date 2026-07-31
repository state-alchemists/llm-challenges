"""Pipeline for processing server logs into an HTML report.

Reads server log entries, extracts errors / user sessions / API latency data,
persists aggregates to SQLite, and writes a report.html summarising:
  - Error summary (message → occurrence count)
  - API latency table (endpoint → average ms)
  - Active session count (users who logged in without logging out)

All configuration is sourced from environment variables; no credentials
or paths are hardcoded.
"""

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration – sourced entirely from environment variables
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("PIPELINE_LOG_FILE", "server.log")
REPORT_PATH: str = os.getenv("PIPELINE_REPORT_PATH", "report.html")
DB_HOST: str = os.getenv("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.getenv("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.getenv("PIPELINE_DB_PASS", "")  # never hardcode

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """An aggregated error record."""

    message: str
    count: int


@dataclass
class ApiCall:
    """A single API call observation."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class ParsedLog:
    """Container for all data extracted from the log file."""

    errors: List[ErrorEntry] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)
    warnings: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Log-line regex patterns
# ---------------------------------------------------------------------------

# Generic prefix: "2024-01-01 12:00:00 LEVEL ..."
_LOG_PREFIX_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>\w+)"
)

# "INFO User 42 logged in" / "INFO User 42 logged out"
_USER_RE = re.compile(
    r"User\s+(?P<uid>\S+)\s+(?P<action>.*)$"
)

# "INFO API /users/profile took 250ms"
_API_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)\s+.*took\s+(?P<ms>\d+)ms"
)

# Any remaining text after "LEVEL "
_MESSAGE_RE = re.compile(
    r"^(?:\S+\s+){2}\w+\s+(?P<msg>.+)$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract(log_path: str) -> ParsedLog:
    """Parse the server log file and return structured data.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ParsedLog containing errors, API calls, active sessions, and warnings.
    """
    path = Path(log_path)
    if not path.exists():
        print(f"Log file {log_path} not found; proceeding with empty data.")
        return ParsedLog()

    error_counts: Dict[str, int] = {}
    api_calls: List[ApiCall] = []
    sessions: Dict[str, str] = {}
    warnings: List[Dict[str, str]] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        prefix_match = _LOG_PREFIX_RE.match(line)
        if not prefix_match:
            continue

        timestamp = prefix_match.group("timestamp")
        level = prefix_match.group("level")
        remainder = line[prefix_match.end():].strip()

        if level == "ERROR":
            msg = _MESSAGE_RE.match(line)
            error_msg = msg.group("msg") if msg else remainder
            error_counts[error_msg] = error_counts.get(error_msg, 0) + 1

        elif level == "INFO":
            user_match = _USER_RE.search(remainder)
            if user_match:
                uid = user_match.group("uid")
                action = user_match.group("action")
                if "logged in" in action:
                    sessions[uid] = timestamp
                elif "logged out" in action:
                    sessions.pop(uid, None)
                continue

            api_match = _API_RE.search(remainder)
            if api_match:
                api_calls.append(ApiCall(
                    timestamp=timestamp,
                    endpoint=api_match.group("endpoint"),
                    latency_ms=int(api_match.group("ms")),
                ))
                continue

        elif level == "WARN":
            msg = _MESSAGE_RE.match(line)
            warnings.append({
                "timestamp": timestamp,
                "message": msg.group("msg") if msg else remainder,
            })

    errors = [ErrorEntry(message=msg, count=c) for msg, c in error_counts.items()]
    return ParsedLog(
        errors=errors,
        api_calls=api_calls,
        active_sessions=sessions,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


@dataclass
class ReportData:
    """Aggregated data ready for report rendering."""

    errors: List[ErrorEntry]
    api_latency: Dict[str, float]
    active_session_count: int


def transform(parsed: ParsedLog) -> ReportData:
    """Compute report-ready aggregates from parsed log data.

    Args:
        parsed: The extracted log data.

    Returns:
        A ReportData with errors, api_latency, and active_session_count,
        ready for the report template.
    """
    # API latency: endpoint → (total_ms, count)
    latency_by_endpoint: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        latency_by_endpoint.setdefault(call.endpoint, []).append(call.latency_ms)

    api_latency = {
        ep: round(sum(times) / len(times), 1)
        for ep, times in latency_by_endpoint.items()
    }

    return ReportData(
        errors=parsed.errors,
        api_latency=api_latency,
        active_session_count=len(parsed.active_sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(parsed: ParsedLog, db_path: str) -> None:
    """Persist aggregated error and API metrics to SQLite.

    Uses parameterized queries exclusively to prevent SQL injection.

    Args:
        parsed: The extracted log data.
        db_path: Path to the SQLite database file.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.now().isoformat()

    # Aggregate errors by message
    error_counts: Dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + entry.count

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    # Aggregate API latencies per endpoint
    latency_by_endpoint: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        latency_by_endpoint.setdefault(call.endpoint, []).append(call.latency_ms)

    for ep, times in latency_by_endpoint.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def load_to_report(report_data: ReportData, report_path: str) -> None:
    """Write the HTML report to disk.

    The report contains three sections matching the original output:
    - Error Summary
    - API Latency table
    - Active Sessions count

    Args:
        report_data: Transformed data with errors, api_latency, and
            active_session_count.
        report_path: Path to write the HTML report.
    """
    errors = report_data.errors
    api_latency = report_data.api_latency
    active_session_count = report_data.active_session_count

    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err in errors:
        lines.append(f"<li><b>{err.message}</b>: {err.count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, avg in api_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Job finished at {datetime.now()}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Reads the log file, transforms the data, persists to the database,
    and writes the HTML report.
    """
    parsed = extract(LOG_FILE)
    report_data = transform(parsed)
    load_to_db(parsed, DB_PATH)
    load_to_report(report_data, REPORT_PATH)


# ---------------------------------------------------------------------------
# Seed data for development / testing
# ---------------------------------------------------------------------------

_SEED_LOG_LINES = """\
2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Database timeout
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
"""


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        Path(LOG_FILE).write_text(_SEED_LOG_LINES, encoding="utf-8")
    run_pipeline()