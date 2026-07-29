"""Refactored server-log pipeline: extract, transform, load with report generation.

Reads server logs, aggregates errors and API latencies, tracks sessions,
persists summaries to SQLite via parameterized queries, and writes an HTML report.
All configuration is sourced from environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration — every value is pulled from the environment, with defaults
# that match the original script so it works out-of-the-box.
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data structures for parsed log entries
# ---------------------------------------------------------------------------
@dataclass
class ErrorEntry:
    """An ERROR-level log event."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user login / logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCallEntry:
    """An API call with measured latency."""
    timestamp: str
    endpoint: str
    latency_ms: int


# ---------------------------------------------------------------------------
# Compiled regexes for robust log-line parsing
# ---------------------------------------------------------------------------
# Format: "2024-01-01 12:00:00 LEVEL rest…"
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<rest>.*)$"
)

# User event: "User <id> <action>"
USER_EVENT_RE = re.compile(
    r"User\s+(?P<user_id>\S+)\s+(?P<action>.*)"
)

# API call: "API <endpoint> took <N>ms"  (latency is optional)
API_CALL_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?"
)


# ---------------------------------------------------------------------------
# Extract — read and parse the log file
# ---------------------------------------------------------------------------
def extract_log_entries(
    log_path: str,
) -> Tuple[List[ErrorEntry], Dict[str, str], List[ApiCallEntry]]:
    """Read the log file and parse every line into typed entries.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple of (errors, active_sessions, api_calls).
        *errors* is a list of ErrorEntry objects.
        *active_sessions* maps user_id to login timestamp for currently
        logged-in users.
        *api_calls* is a list of ApiCallEntry objects.
    """
    errors: List[ErrorEntry] = []
    sessions: Dict[str, str] = {}
    api_calls: List[ApiCallEntry] = []

    if not os.path.exists(log_path):
        return errors, sessions, api_calls

    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp: str = match.group("timestamp")
            level: str = match.group("level")
            rest: str = match.group("rest")

            if level == "ERROR":
                errors.append(ErrorEntry(
                    timestamp=timestamp, message=rest,
                ))

            elif level == "INFO":
                user_match = USER_EVENT_RE.match(rest)
                if user_match:
                    uid = user_match.group("user_id")
                    action = user_match.group("action")
                    _update_sessions(sessions, uid, action, timestamp)
                    continue

                api_match = API_CALL_RE.match(rest)
                if api_match:
                    endpoint = api_match.group("endpoint")
                    ms = int(api_match.group("ms") or 0)
                    api_calls.append(ApiCallEntry(
                        timestamp=timestamp,
                        endpoint=endpoint,
                        latency_ms=ms,
                    ))

            # WARN lines are parsed but not aggregated for the report

    return errors, sessions, api_calls


def _update_sessions(
    sessions: Dict[str, str],
    user_id: str,
    action: str,
    timestamp: str,
) -> None:
    """Track active user sessions from login/logout events.

    Mutates *sessions* in place: adds on login, removes on logout.
    """
    if "logged in" in action:
        sessions[user_id] = timestamp
    elif "logged out" in action and user_id in sessions:
        sessions.pop(user_id)


# ---------------------------------------------------------------------------
# Transform — aggregate raw entries into report-ready summaries
# ---------------------------------------------------------------------------
def transform_error_summary(errors: List[ErrorEntry]) -> Dict[str, int]:
    """Aggregate ERROR entries into a message → count mapping.

    Args:
        errors: Parsed error entries from the log.

    Returns:
        Dictionary mapping each distinct error message to its occurrence count.
    """
    summary: Dict[str, int] = {}
    for entry in errors:
        summary[entry.message] = summary.get(entry.message, 0) + 1
    return summary


def transform_api_stats(
    api_calls: List[ApiCallEntry],
) -> Dict[str, List[int]]:
    """Group API call latencies by endpoint.

    Args:
        api_calls: Parsed API call entries from the log.

    Returns:
        Dictionary mapping each endpoint to its list of observed latencies.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.latency_ms)
    return stats


# ---------------------------------------------------------------------------
# Load — persist to SQLite and write the HTML report
# ---------------------------------------------------------------------------
def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    api_stats: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_summary: Error message → occurrence count mapping.
        api_stats: Endpoint → list of latency values mapping.
    """
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_stats.items():
        avg_ms = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: Dict[str, int],
    api_stats: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> str:
    """Render the HTML report from aggregated metrics.

    Args:
        error_summary: Error message → occurrence count mapping.
        api_stats: Endpoint → list of latency values mapping.
        active_sessions: Currently logged-in user_id → timestamp mapping.

    Returns:
        Complete HTML document as a string.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
    ]

    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, times in api_stats.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main — orchestrate the ETL pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the extract-transform-load pipeline and generate the report."""
    errors, sessions, api_calls = extract_log_entries(LOG_FILE)

    error_summary = transform_error_summary(errors)
    api_stats = transform_api_stats(api_calls)

    load_to_database(DB_PATH, error_summary, api_stats)

    report_html = generate_report(error_summary, api_stats, sessions)
    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write(report_html)

    print(f"Pipeline finished at {datetime.datetime.now()}")


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