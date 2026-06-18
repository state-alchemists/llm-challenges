"""
Log processing pipeline: Extract → Transform → Load.

Parses server logs, aggregates error counts and API latency metrics,
persists them to SQLite, and generates an HTML report.

Configuration (all via environment variables):
    LOG_FILE        Path to the server log (default: server.log)
    DB_PATH         Path to the SQLite database (default: metrics.db)
    DB_HOST         Database host (default: localhost)
    DB_PORT         Database port (default: 5432)
    DB_USER         Database user (default: admin)
    DB_PASS         Database password (default: password123)
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ParsedError(NamedTuple):
    """A single parsed ERROR-level log line."""

    timestamp: str
    message: str


class ParsedApiCall(NamedTuple):
    """A single parsed INFO log line containing an API latency record."""

    timestamp: str
    endpoint: str
    latency_ms: int


class ParsedSession(NamedTuple):
    """A single parsed INFO log line containing a user session event."""

    timestamp: str
    user_id: str
    action: str  # "logged in" or "logged out"


class LogMetrics(NamedTuple):
    """Aggregated metrics produced by the Transform phase."""

    errors: dict[str, int]  # message -> count
    api_latency: dict[str, list[int]]  # endpoint -> list of latencies (ms)
    active_sessions: int


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")

# Compiled regex patterns (module-level for performance)
_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR)\s+(?P<message>.*)$"
)
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO)\s+API (?P<endpoint>\S+)\s+took (?P<latency>\d+)ms$"
)
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO)\s+User (?P<user_id>\S+)\s+(?P<action>logged in|logged out)$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------


def parse_log_line(line: str) -> ParsedError | ParsedApiCall | ParsedSession | None:
    """
    Parse a single log line using regex.

    Returns the appropriate NamedTuple per line type, or None if the line
    does not match any known pattern.
    """
    line = line.strip()
    if not line:
        return None

    if m := _RE_ERROR.match(line):
        return ParsedError(timestamp=m["timestamp"], message=m["message"])

    if m := _RE_API.match(line):
        return ParsedApiCall(
            timestamp=m["timestamp"],
            endpoint=m["endpoint"],
            latency_ms=int(m["latency"]),
        )

    if m := _RE_USER.match(line):
        return ParsedSession(
            timestamp=m["timestamp"],
            user_id=m["user_id"],
            action=m["action"],
        )

    return None


def extract_logs(log_path: str) -> tuple[list[ParsedError], list[ParsedApiCall], list[ParsedSession]]:
    """
    Read and parse every line in *log_path*.

    Returns three parallel lists: errors, api_calls, sessions.
    Lines that don't match any known pattern are skipped silently.
    """
    errors: list[ParsedError] = []
    api_calls: list[ParsedApiCall] = []
    sessions: list[ParsedSession] = []

    if not os.path.exists(log_path):
        return errors, api_calls, sessions

    with open(log_path, "r") as f:
        for line in f:
            parsed = parse_log_line(line)
            if isinstance(parsed, ParsedError):
                errors.append(parsed)
            elif isinstance(parsed, ParsedApiCall):
                api_calls.append(parsed)
            elif isinstance(parsed, ParsedSession):
                sessions.append(parsed)

    return errors, api_calls, sessions


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ParsedError]) -> dict[str, int]:
    """
    Count occurrences of each unique error message.

    Returns a dict mapping error message → occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def aggregate_api_latency(api_calls: list[ParsedApiCall]) -> dict[str, list[int]]:
    """
    Group API calls by endpoint, collecting latency values.

    Returns a dict mapping endpoint → list of latency measurements (ms).
    """
    grouped: dict[str, list[int]] = {}
    for call in api_calls:
        grouped.setdefault(call.endpoint, []).append(call.latency_ms)
    return grouped


def track_sessions(sessions: list[ParsedSession]) -> int:
    """
    Compute the number of currently active sessions.

    A user is considered active from their "logged in" event until their
    "logged out" event. Users who logged in but never logged out are
    counted as still active.
    """
    active: set[str] = set()
    for sess in sessions:
        if sess.action == "logged in":
            active.add(sess.user_id)
        elif sess.action == "logged out":
            active.discard(sess.user_id)
    return len(active)


def transform(
    errors: list[ParsedError], api_calls: list[ParsedApiCall], sessions: list[ParsedSession]
) -> LogMetrics:
    """
    Run all transformation steps and return a single LogMetrics bundle.
    """
    return LogMetrics(
        errors=aggregate_errors(errors),
        api_latency=aggregate_api_latency(api_calls),
        active_sessions=track_sessions(sessions),
    )


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------


def write_to_db(db_path: str, metrics: LogMetrics) -> None:
    """
    Persist *metrics* to the SQLite database at *db_path*.

    Creates the tables if they do not exist.
    Uses parameterized queries to prevent SQL injection.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt     TEXT,
            message TEXT,
            count  INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt       TEXT,
            endpoint TEXT,
            avg_ms   REAL
        )
        """
    )

    now = datetime.datetime.now().isoformat()

    # Parameterized INSERT — safe against injection
    for msg, count in metrics.errors.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, latencies in metrics.api_latency.items():
        avg_ms = sum(latencies) / len(latencies)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def _format_html_table_row(cells: list[str]) -> str:
    """Return an HTML table row given a list of cell values."""
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>\n"


def generate_html_report(metrics: LogMetrics, output_path: str) -> None:
    """
    Write an HTML report summarizing errors, API latency, and active sessions.

    The report layout matches the original pipeline output.
    """
    rows = []
    rows.append("<html>")
    rows.append("<head><title>System Report</title></head>")
    rows.append("<body>")

    # Error summary
    rows.append("<h1>Error Summary</h1>")
    if metrics.errors:
        rows.append("<ul>")
        for msg, count in metrics.errors.items():
            rows.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
        rows.append("</ul>")
    else:
        rows.append("<p>No errors recorded.</p>")

    # API latency table
    rows.append("<h2>API Latency</h2>")
    rows.append("<table border='1'>")
    rows.append(_format_html_table_row(["Endpoint", "Avg (ms)"]))
    for endpoint, latencies in metrics.api_latency.items():
        avg = round(sum(latencies) / len(latencies), 1)
        rows.append(_format_html_table_row([endpoint, str(avg)]))
    rows.append("</table>")

    # Active sessions
    rows.append("<h2>Active Sessions</h2>")
    rows.append(f"<p>{metrics.active_sessions} user(s) currently active</p>")

    rows.append("</body>")
    rows.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(rows))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Execute the full Extract → Transform → Load pipeline.

    Reads configuration from environment variables, parses the log file,
    aggregates metrics, writes to SQLite, and emits report.html.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    # Extract
    errors, api_calls, sessions = extract_logs(LOG_FILE)

    # Transform
    metrics = transform(errors, api_calls, sessions)

    # Load
    write_to_db(DB_PATH, metrics)
    generate_html_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bootstrap a sample log when the file doesn't exist (mirrors original behaviour)
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as f:
            f.write("\n".join(sample_lines) + "\n")

    run_pipeline()