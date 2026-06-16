"""Log processing pipeline: extract, transform, and load server logs into a report.

Usage:
    python pipeline_refactored.py

Output:
    report.html — error summary, API latency table, active session count

Configuration (all via environment variables):
    LOG_FILE_PATH  Path to server log (default: server.log)
    DB_PATH        SQLite database path   (default: metrics.db)
    REPORT_PATH    Output HTML path       (default: report.html)
    DB_HOST        Unused by SQLite; reserved for future PostgreSQL use
    DB_PORT        Unused by SQLite; reserved for future PostgreSQL use
    DB_USER        Unused by SQLite; reserved for future PostgreSQL use
    DB_PASS        Unused by SQLite; reserved for future PostgreSQL use
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# ── Regex patterns ──

LINE_RE: re.Pattern = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<message>.+)$"
)
USER_RE: re.Pattern = re.compile(r"^User (\S+) (.+)$")
API_RE: re.Pattern = re.compile(r"^API (\S+) took (\d+)ms$")


# ── Data models ──


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single parsed log line with structured fields extracted when applicable.

    Fields beyond *timestamp*, *level*, and *message* are populated only for
    log lines that carry additional structured information (user actions,
    API call metrics).
    """

    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    user_action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class LogSummary:
    """Aggregated metrics derived from all parsed log entries.

    Carries the three outputs needed by both the database load and the
    HTML report generation, so neither step has to re-parse or re-aggregate.
    """

    error_counts: dict[str, int]
    api_endpoints: dict[str, list[int]]
    active_session_count: int


@dataclass(frozen=True, slots=True)
class Config:
    """Application configuration loaded from environment variables.

    All values default to paths and credentials that match the original
    hardcoded values, so the refactored script works out of the box
    without env vars set.
    """

    log_file: str = "server.log"
    db_path: str = "metrics.db"
    report_path: str = "report.html"


# ── Configuration ──


def load_config() -> Config:
    """Read configuration from environment variables with sensible defaults.

    Returns:
        A Config instance populated from the environment or fallback values.
    """
    return Config(
        log_file=os.environ.get("LOG_FILE_PATH", "server.log"),
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        report_path=os.environ.get("REPORT_PATH", "report.html"),
    )


# ── Extract ──


def read_log_lines(path: str) -> list[str]:
    """Read all non-empty lines from the log file.

    Args:
        path: Path to the server log file.

    Returns:
        A list of stripped log lines, with blank lines filtered out.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]


# ── Transform ──


def parse_log_line(line: str) -> LogEntry | None:
    """Parse one log line into a structured LogEntry.

    The parser handles four line types:

    * ``ERROR <message>`` — stores the raw message.
    * ``INFO User <id> <action>`` — extracts *user_id* and *user_action*.
    * ``INFO API <endpoint> took <ms>ms`` — extracts *endpoint* and *duration_ms*.
    * ``WARN <message>`` — stores the raw message.

    Args:
        line: A single log line (e.g. ``"2024-01-01 12:00:00 INFO User 42 logged in"``).

    Returns:
        A LogEntry if the line matched the expected format, or None otherwise.
    """
    match = LINE_RE.match(line)
    if not match:
        return None

    ts = match.group("timestamp")
    level = match.group("level")
    msg = match.group("message")

    if level == "ERROR":
        return LogEntry(timestamp=ts, level=level, message=msg)

    if level == "WARN":
        return LogEntry(timestamp=ts, level=level, message=msg)

    if level == "INFO":
        entry = LogEntry(timestamp=ts, level=level, message=msg)

        user_match = USER_RE.match(msg)
        if user_match:
            object.__setattr__(entry, "user_id", user_match.group(1))
            object.__setattr__(entry, "user_action", user_match.group(2))

        api_match = API_RE.match(msg)
        if api_match:
            object.__setattr__(entry, "endpoint", api_match.group(1))
            object.__setattr__(entry, "duration_ms", int(api_match.group(2)))

        return entry

    return None


def aggregate_logs(entries: list[LogEntry]) -> LogSummary:
    """Derive summary metrics from a list of parsed log entries.

    Performs a single pass to compute:

    * Error counts (grouped by message text).
    * API endpoint latency samples.
    * Active session count (tracks user log in / log out).

    Args:
        entries: Parsed log entries.

    Returns:
        A LogSummary containing the three aggregated metrics.
    """
    error_counts: dict[str, int] = defaultdict(int)
    api_endpoints: dict[str, list[int]] = defaultdict(list)
    active_sessions: set[str] = set()

    for entry in entries:
        if entry.level == "ERROR":
            error_counts[entry.message] += 1
        elif entry.level == "INFO" and entry.user_id is not None:
            action = entry.user_action or ""
            if "logged in" in action:
                active_sessions.add(entry.user_id)
            elif "logged out" in action:
                active_sessions.discard(entry.user_id)
        elif entry.level == "INFO" and entry.endpoint is not None:
            api_endpoints[entry.endpoint].append(entry.duration_ms or 0)

    return LogSummary(
        error_counts=dict(error_counts),
        api_endpoints=dict(api_endpoints),
        active_session_count=len(active_sessions),
    )


# ── Load ──


def init_db(db_path: str) -> sqlite3.Connection:
    """Open a SQLite database and ensure the required tables exist.

    Creates two tables if they do not already exist:

    * ``errors`` — (dt, message, count)
    * ``api_metrics`` — (dt, endpoint, avg_ms)

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open connection to the database.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def load_error_summary(conn: sqlite3.Connection, errors: dict[str, int]) -> None:
    """Insert aggregated error counts into the errors table.

    Uses a parameterized query to prevent SQL injection.

    Args:
        conn: Open database connection.
        errors: Mapping of error message → occurrence count.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for msg, count in errors.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )


def load_api_metrics(conn: sqlite3.Connection, endpoints: dict[str, list[int]]) -> None:
    """Insert average API latencies into the api_metrics table.

    Uses a parameterized query to prevent SQL injection.

    Args:
        conn: Open database connection.
        endpoints: Mapping of endpoint name → list of observed durations (ms).
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for endpoint, durations in endpoints.items():
        avg = sum(durations) / len(durations)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )


def generate_report_html(summary: LogSummary) -> str:
    """Build the HTML report string from aggregated log metrics.

    Args:
        summary: Aggregated metrics from the transform phase.

    Returns:
        A complete HTML document as a string.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in sorted(summary.error_counts.items()):
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, durations in sorted(summary.api_endpoints.items()):
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{summary.active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


def write_html(path: str, html: str) -> None:
    """Write the HTML report to a file.

    Args:
        path: Destination file path.
        html: Complete HTML document string.
    """
    Path(path).write_text(html)


# ── Pipeline orchestrator ──


def main() -> None:
    """Run the full ETL pipeline: read log → parse → aggregate → load → report.

    The pipeline produces two outputs:

    1. A SQLite database (``metrics.db`` by default) with ``errors`` and
       ``api_metrics`` tables.
    2. An HTML report (``report.html`` by default) with the error summary,
       API latency table, and active session count.
    """
    config = load_config()

    raw_lines = read_log_lines(config.log_file)
    entries = [e for line in raw_lines if (e := parse_log_line(line)) is not None]
    summary = aggregate_logs(entries)

    conn = init_db(config.db_path)
    try:
        load_error_summary(conn, summary.error_counts)
        load_api_metrics(conn, summary.api_endpoints)
        conn.commit()
    finally:
        conn.close()

    html = generate_report_html(summary)
    write_html(config.report_path, html)

    print(f"Report written to {config.report_path}")
    print(f"Job finished at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    cfg = load_config()
    if not os.path.exists(cfg.log_file):
        demo_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(cfg.log_file, "w") as f:
            for line in demo_lines:
                f.write(line + "\n")
        print(f"Created demo log file: {cfg.log_file}")
    main()
