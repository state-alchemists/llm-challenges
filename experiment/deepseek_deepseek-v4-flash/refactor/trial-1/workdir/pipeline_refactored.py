"""
Refactored server log pipeline: Extract -> Transform -> Load.

Processes a server log file, stores metrics in SQLite (parameterised queries),
and generates an HTML report (error summary, API latency table, active session count).

Usage:
    export LOG_FILE_PATH=server.log
    export METRICS_DB_PATH=metrics.db
    python pipeline_refactored.py
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration  (env-var driven)
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Application configuration, loaded from environment variables.

    Every value falls back to a sensible default so the script runs
    out of the box with the sample data.
    """

    log_file: str = field(
        default_factory=lambda: os.getenv("LOG_FILE_PATH", "server.log")
    )
    db_path: str = field(
        default_factory=lambda: os.getenv("METRICS_DB_PATH", "metrics.db")
    )
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(
        default_factory=lambda: int(os.getenv("DB_PORT", "5432"))
    )
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "admin"))
    db_pass: str = field(default_factory=lambda: os.getenv("DB_PASS", "password123"))
    report_output: str = field(
        default_factory=lambda: os.getenv("REPORT_OUTPUT_PATH", "report.html")
    )


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults."""
    return Config()


# ---------------------------------------------------------------------------
# Extract: typed data structures for parsed log entries
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """A single ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class ApiEntry:
    """A single INFO-level API latency measurement."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class UserEntry:
    """A single INFO-level user action (login / logout)."""

    timestamp: str
    user_id: str
    action: str  # "logged in" | "logged out"


@dataclass
class WarnEntry:
    """A single WARN-level log entry."""

    timestamp: str
    message: str


# ---------------------------------------------------------------------------
# Extract: regex-based log-line parsing
# ---------------------------------------------------------------------------

# Full log line:  YYYY-MM-DD HH:MM:SS LEVEL rest-of-line
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.+)$"
)

# Sub-grammars for the INFO rest-of-line
_USER_RE = re.compile(r"^User (\d+) (logged in|logged out)$")
_API_RE = re.compile(r"^API (\S+) took (\d+)ms$")

# Union of all possible parsed-entry types
LogEntry = ErrorEntry | ApiEntry | UserEntry | WarnEntry


def _parse_error(ts: str, rest: str) -> ErrorEntry:
    """Build an ErrorEntry from an ERROR-level remainder."""
    return ErrorEntry(timestamp=ts, message=rest.strip())


def _parse_warn(ts: str, rest: str) -> WarnEntry:
    """Build a WarnEntry from a WARN-level remainder."""
    return WarnEntry(timestamp=ts, message=rest.strip())


def _parse_info(ts: str, rest: str) -> ApiEntry | UserEntry | None:
    """Parse an INFO-level remainder into an API or User entry.

    Returns an :class:`ApiEntry` or :class:`UserEntry`, or ``None`` when
    the line is not a recognised INFO sub-type.
    """
    m = _USER_RE.match(rest)
    if m:
        return UserEntry(timestamp=ts, user_id=m.group(1), action=m.group(2))

    m = _API_RE.match(rest)
    if m:
        return ApiEntry(timestamp=ts, endpoint=m.group(1), duration_ms=int(m.group(2)))

    return None


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single server log line into a structured record.

    Args:
        line: A raw log line (trailing newline is stripped internally).

    Returns:
        An :class:`ErrorEntry`, :class:`WarnEntry`, :class:`ApiEntry`,
        or :class:`UserEntry`, depending on the log level.
        Returns ``None`` when the line does not match the expected format.
    """
    m = _LINE_RE.match(line.rstrip("\n"))
    if not m:
        return None

    level = m.group("level")
    ts = m.group("ts")
    rest = m.group("rest")

    if level == "ERROR":
        return _parse_error(ts, rest)
    if level == "WARN":
        return _parse_warn(ts, rest)

    # INFO lines need sub-parsing
    return _parse_info(ts, rest)


# ---------------------------------------------------------------------------
# Extract: orchestrate file reading
# ---------------------------------------------------------------------------


@dataclass
class ExtractedData:
    """Container for all parsed log entries, grouped by category."""

    errors: list[ErrorEntry] = field(default_factory=list)
    api_calls: list[ApiEntry] = field(default_factory=list)
    user_actions: list[UserEntry] = field(default_factory=list)
    warns: list[WarnEntry] = field(default_factory=list)


def extract_logs(path: str) -> ExtractedData:
    """Read and parse a server log file.

    Args:
        path: Path to the server log file.  Returns an empty
              :class:`ExtractedData` when the file does not exist.

    Returns:
        An ``ExtractedData`` instance with all parsed entries.
    """
    data = ExtractedData()
    if not os.path.exists(path):
        return data

    with open(path, "r") as f:
        for line in f:
            result = parse_log_line(line)
            if result is None:
                continue
            entry = result
            if isinstance(entry, ErrorEntry):
                data.errors.append(entry)
            elif isinstance(entry, WarnEntry):
                data.warns.append(entry)
            elif isinstance(entry, ApiEntry):
                data.api_calls.append(entry)
            elif isinstance(entry, UserEntry):
                data.user_actions.append(entry)
    return data


# ---------------------------------------------------------------------------
# Transform: aggregate raw entries into report-ready structures
# ---------------------------------------------------------------------------


def aggregate_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Count occurrences of each distinct error message.

    Args:
        errors: Error entries parsed from the log.

    Returns:
        Mapping of error message -> occurrence count.
    """
    counts: dict[str, int] = {}
    for e in errors:
        counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def compute_api_latency(api_calls: list[ApiEntry]) -> dict[str, float]:
    """Compute the average latency (ms) per API endpoint.

    Args:
        api_calls: API latency entries parsed from the log.

    Returns:
        Mapping of endpoint path -> average latency in milliseconds.
    """
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}

    for call in api_calls:
        totals[call.endpoint] = totals.get(call.endpoint, 0.0) + call.duration_ms
        counts[call.endpoint] = counts.get(call.endpoint, 0) + 1

    return {ep: totals[ep] / counts[ep] for ep in totals}


def track_active_sessions(actions: list[UserEntry]) -> dict[str, str]:
    """Process login/logout events to determine currently active sessions.

    Args:
        actions: User-action entries parsed from the log.

    Returns:
        Mapping of ``user_id -> login_timestamp`` for sessions that are
        still active after processing all events.
    """
    sessions: dict[str, str] = {}

    for action in actions:
        if action.action == "logged in":
            sessions[action.user_id] = action.timestamp
        elif action.action == "logged out" and action.user_id in sessions:
            del sessions[action.user_id]

    return sessions


# ---------------------------------------------------------------------------
# Load: persist to SQLite  (parameterised queries — no injection)
# ---------------------------------------------------------------------------


def _init_db(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and ensure required tables exist.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Open connection (caller must close).
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def write_db(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    db_path: str,
) -> None:
    """Persist aggregated metrics to SQLite.

    Uses parameterised queries (``?`` placeholders) — no string formatting
    that could introduce SQL injection.

    Args:
        error_counts: Error message -> occurrence count.
        api_stats: Endpoint -> average latency (ms).
        db_path: Path to the SQLite database file.
    """
    now = datetime.datetime.now().isoformat()
    conn = _init_db(db_path)

    with conn:
        conn.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            [(now, msg, cnt) for msg, cnt in error_counts.items()],
        )
        conn.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            [(now, ep, avg) for ep, avg in api_stats.items()],
        )

    conn.close()


# ---------------------------------------------------------------------------
# Load: generate HTML report
# ---------------------------------------------------------------------------


def _build_html(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    active_sessions: int,
) -> str:
    """Build the full HTML report document.

    Args:
        error_counts: Error message -> occurrence count.
        api_stats: Endpoint -> average latency (ms).
        active_sessions: Number of currently active user sessions.

    Returns:
        Complete HTML document as a string.
    """
    parts = [
        "<html>\n<head><title>System Report</title></head>\n<body>",
        "<h1>Error Summary</h1>\n<ul>",
    ]
    for msg, cnt in sorted(error_counts.items(), key=lambda x: -x[1]):
        parts.append(f"<li><b>{msg}</b>: {cnt} occurrences</li>")
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>\n<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in sorted(api_stats.items()):
        parts.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{active_sessions} user(s) currently active</p>")
    parts.append("</body>\n</html>")

    return "\n".join(parts)


def write_report(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    active_sessions: int,
    output_path: str,
) -> None:
    """Write the HTML report to disk.

    Args:
        error_counts: Error message -> occurrence count.
        api_stats: Endpoint -> average latency (ms).
        active_sessions: Number of currently active user sessions.
        output_path: Destination path for the ``.html`` file.
    """
    html = _build_html(error_counts, api_stats, active_sessions)
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Report written to {output_path}")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full ETL pipeline: extract, transform, load."""
    cfg = load_config()
    print(f"Processing log: {cfg.log_file}")

    # --- Extract ---
    data = extract_logs(cfg.log_file)
    print(
        f"Parsed: {len(data.errors)} errors, {len(data.api_calls)} API calls, "
        f"{len(data.user_actions)} user actions, {len(data.warns)} warnings"
    )

    # --- Transform ---
    error_counts = aggregate_errors(data.errors)
    api_stats = compute_api_latency(data.api_calls)
    sessions = track_active_sessions(data.user_actions)

    # --- Load ---
    write_db(error_counts, api_stats, cfg.db_path)
    write_report(error_counts, api_stats, len(sessions), cfg.report_output)

    print(f"Job finished at {datetime.datetime.now()}")


def _seed_sample_log(path: str) -> None:
    """Write a sample server log file for testing / demo purposes.

    The sample data exercises every recognised log level so the pipeline
    can be verified immediately after creation.
    """
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")
    print(f"Sample log written to {path}")


if __name__ == "__main__":
    cfg = load_config()
    if not os.path.exists(cfg.log_file):
        _seed_sample_log(cfg.log_file)
    main()
