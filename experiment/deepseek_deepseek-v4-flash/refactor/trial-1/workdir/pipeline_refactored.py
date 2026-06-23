"""
Pipeline: extract server logs -> transform (aggregate/analyze) -> load (DB + HTML report).

Reads a server log file, parses entries with regex, aggregates errors and API
latency metrics, tracks user sessions, writes results to a SQLite database, and
produces a report.html summary.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)
_USER_EVENT_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_CALL_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    report_file: str


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults.

    Returns:
        Config populated from env vars ``DB_PATH`` (default ``metrics.db``),
        ``LOG_FILE`` (default ``server.log``), and ``REPORT_FILE`` (default
        ``report.html``).
    """
    return Config(
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        log_file=os.environ.get("LOG_FILE", "server.log"),
        report_file=os.environ.get("REPORT_FILE", "report.html"),
    )


# ---------------------------------------------------------------------------
# Extract — log parsing
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """A single parsed log entry."""

    timestamp: str
    level: str  # 'ERROR' | 'INFO' | 'WARN'
    message: str


def extract_logs(path: str) -> list[LogEntry]:
    """Read and parse a log file into structured entries.

    Each line must match the format ``YYYY-MM-DD HH:MM:SS LEVEL message``.
    Lines that do not match are silently skipped.

    Args:
        path: Filesystem path to the log file.

    Returns:
        List of parsed :class:`LogEntry` instances.
    """
    entries: list[LogEntry] = []

    if not os.path.exists(path):
        return entries

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = _LOG_LINE_RE.match(line)
            if m is None:
                continue
            entries.append(
                LogEntry(
                    timestamp=m.group("timestamp"),
                    level=m.group("level"),
                    message=m.group("message"),
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Transform — aggregation & analysis
# ---------------------------------------------------------------------------


@dataclass
class ParsedLogs:
    """Container for all extracted and derived data."""

    error_counts: dict[str, int] = field(default_factory=dict)
    """Error message -> occurrence count."""

    api_calls: dict[str, list[int]] = field(default_factory=dict)
    """Endpoint name -> list of durations in ms."""

    active_users: dict[str, str] = field(default_factory=dict)
    """User ID -> login timestamp for currently active sessions."""


def aggregate_events(entries: list[LogEntry]) -> ParsedLogs:
    """Classify log entries and aggregate errors, API metrics, and session state.

    Args:
        entries: Parsed log entries from :func:`extract_logs`.

    Returns:
        Aggregated data in a :class:`ParsedLogs` container.
    """
    result = ParsedLogs()

    for entry in entries:
        if entry.level == "ERROR":
            result.error_counts[entry.message] = (
                result.error_counts.get(entry.message, 0) + 1
            )
        elif entry.level == "WARN":
            # Warnings are tracked but not part of the current report output.
            pass
        elif entry.level == "INFO":
            _parse_info(entry, result)

    return result


def _parse_info(entry: LogEntry, result: ParsedLogs) -> None:
    """Parse an INFO-level message for user events or API calls.

    Mutates *result* in place.

    Args:
        entry: The INFO log entry to parse.
        result: The aggregate container to update.
    """
    # Try user event first (login / logout).
    user_m = _USER_EVENT_RE.match(entry.message)
    if user_m:
        uid = user_m.group("user_id")
        action = user_m.group("action")
        if "logged in" in action:
            result.active_users[uid] = entry.timestamp
        elif "logged out" in action and uid in result.active_users:
            del result.active_users[uid]
        return

    # Try API call.
    api_m = _API_CALL_RE.match(entry.message)
    if api_m:
        endpoint = api_m.group("endpoint")
        duration = int(api_m.group("duration"))
        result.api_calls.setdefault(endpoint, []).append(duration)


# ---------------------------------------------------------------------------
# Load — database write
# ---------------------------------------------------------------------------


def _init_db(conn: sqlite3.Connection) -> None:
    """Create schema tables if they do not exist.

    Args:
        conn: Open SQLite connection.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors " "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_to_db(db_path: str, parsed: ParsedLogs) -> None:
    """Write aggregated data into a SQLite database.

    Uses parameterised queries to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        parsed: Aggregated data to persist.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        now = datetime.datetime.now().isoformat()

        for msg, count in parsed.error_counts.items():
            conn.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, durations in parsed.api_calls.items():
            avg = sum(durations) / len(durations)
            conn.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Load — HTML report
# ---------------------------------------------------------------------------


def _build_error_section(error_counts: dict[str, int]) -> str:
    """Build the HTML error summary as an unordered list.

    Args:
        error_counts: Error message -> occurrence count.

    Returns:
        HTML ``<h1>`` and ``<ul>`` block.
    """
    lines = ["<h1>Error Summary</h1>\n<ul>"]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def _build_api_table(api_calls: dict[str, list[int]]) -> str:
    """Build the HTML API latency table.

    Args:
        api_calls: Endpoint -> list of durations in ms.

    Returns:
        HTML ``<h2>`` and ``<table>`` block.
    """
    lines = [
        "<h2>API Latency</h2>\n<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for ep, durations in api_calls.items():
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _build_session_count(active_users: dict[str, str]) -> str:
    """Build the HTML session-count paragraph.

    Args:
        active_users: User ID -> login timestamp mapping.

    Returns:
        HTML ``<h2>`` and ``<p>`` block.
    """
    return (
        "<h2>Active Sessions</h2>\n"
        f"<p>{len(active_users)} user(s) currently active</p>"
    )


def generate_report(parsed: ParsedLogs) -> str:
    """Produce a complete HTML report document.

    Args:
        parsed: Aggregated log data.

    Returns:
        Complete HTML document as a string.
    """
    sections = [
        _build_error_section(parsed.error_counts),
        _build_api_table(parsed.api_calls),
        _build_session_count(parsed.active_users),
    ]
    body = "\n".join(sections)
    return (
        "<html>\n<head><title>System Report</title></head>\n"
        f"<body>\n{body}\n</body>\n</html>"
    )


def write_report(html: str, path: str) -> None:
    """Write the HTML report to a file.

    Args:
        html: Complete HTML document.
        path: Output file path.
    """
    with open(path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract -> Transform -> Load pipeline."""
    config = load_config()

    entries = extract_logs(config.log_file)
    parsed = aggregate_events(entries)

    load_to_db(config.db_path, parsed)

    html = generate_report(parsed)
    write_report(html, config.report_file)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _log_file = os.environ.get("LOG_FILE", "server.log")
    if not os.path.exists(_log_file):
        with open(_log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
