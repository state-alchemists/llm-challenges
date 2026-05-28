"""Pipeline: Extract, Transform, and Load server log data into reports.

Reads server logs, parses them with regex, aggregates errors and API
latency, tracks user sessions, then writes both a SQLite database and
an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

_LOG_FILE_DEFAULT = "server.log"
_DB_PATH_DEFAULT = "metrics.db"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    log_file: str
    db_path: str
    # DB_HOST / DB_PORT / DB_USER / DB_PASS are declared to document the
    # intended connection surface but are not used by SQLite. A production
    # variant would pass them to a real DB driver.
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Create Config from environment variables, falling back to defaults.

    Environment variables (all optional):
      PIPELINE_LOG_FILE  — path to the server log
      PIPELINE_DB_PATH   — path to the SQLite database
      PIPELINE_DB_HOST   — database hostname
      PIPELINE_DB_PORT   — database port
      PIPELINE_DB_USER   — database user
      PIPELINE_DB_PASS   — database password
    """
    return Config(
        log_file=os.environ.get("PIPELINE_LOG_FILE", _LOG_FILE_DEFAULT),
        db_path=os.environ.get("PIPELINE_DB_PATH", _DB_PATH_DEFAULT),
        db_host=os.environ.get("PIPELINE_DB_HOST", "localhost"),
        db_port=int(os.environ.get("PIPELINE_DB_PORT", "5432")),
        db_user=os.environ.get("PIPELINE_DB_USER", "admin"),
        db_pass=os.environ.get("PIPELINE_DB_PASS", ""),
    )


# ---------------------------------------------------------------------------
# Extract — read and parse raw log lines
# ---------------------------------------------------------------------------

# Matches: <date> <time> <LEVEL> <message ...>
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<msg>.+)$"
)
# Sub-patterns for INFO lines
_USER_ACTION_RE = re.compile(r"^User (?P<uid>\d+) (?P<action>.+)$")
_API_CALL_RE = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)


@dataclass
class LogEntry:
    """A single parsed log line."""

    timestamp: str
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None


def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse one log line into a ``LogEntry``, or return ``None``.

    The expected format is::

        YYYY-MM-DD HH:MM:SS LEVEL message

    INFO lines are further classified into user actions and API calls.
    """
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None

    entry = LogEntry(
        timestamp=m.group("ts"),
        level=m.group("level"),
        message=m.group("msg"),
    )

    if entry.level == "INFO":
        user_m = _USER_ACTION_RE.match(entry.message)
        if user_m:
            entry.user_id = user_m.group("uid")
            entry.action = user_m.group("action")
        else:
            api_m = _API_CALL_RE.match(entry.message)
            if api_m:
                entry.endpoint = api_m.group("endpoint")
                entry.duration_ms = int(api_m.group("duration"))

    return entry


def extract_logs(filepath: str) -> list[LogEntry]:
    """Read *filepath* and return all successfully parsed log entries."""
    entries: list[LogEntry] = []
    if not os.path.exists(filepath):
        return entries

    with open(filepath, "r") as f:
        for line in f:
            parsed = parse_log_line(line.rstrip("\n"))
            if parsed is not None:
                entries.append(parsed)
    return entries


# ---------------------------------------------------------------------------
# Transform — aggregate parsed data into summary structures
# ---------------------------------------------------------------------------


def aggregate_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: dict[str, int] = {}
    for e in entries:
        if e.level == "ERROR":
            counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def compute_api_latency(entries: list[LogEntry]) -> dict[str, float]:
    """Return average latency (ms) per API endpoint."""
    totals: dict[str, list[int]] = {}
    for e in entries:
        if e.endpoint is not None and e.duration_ms is not None:
            totals.setdefault(e.endpoint, []).append(e.duration_ms)
    return {
        ep: sum(times) / len(times) for ep, times in totals.items()
    }


def track_active_sessions(entries: list[LogEntry]) -> int:
    """Track login/logout events and return the number of active sessions.

    The original logic treats this as a set of currently-logged-in users.
    """
    active: set[str] = set()
    for e in entries:
        if e.level == "INFO" and e.user_id is not None and e.action is not None:
            if "logged in" in e.action:
                active.add(e.user_id)
            elif "logged out" in e.action:
                active.discard(e.user_id)
    return len(active)


# ---------------------------------------------------------------------------
# Load — persist to database and generate the HTML report
# ---------------------------------------------------------------------------


def init_database(db_path: str) -> sqlite3.Connection:
    """Open (or create) the database and ensure required tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def store_errors(
    conn: sqlite3.Connection, errors: dict[str, int]
) -> None:
    """Insert aggregated error counts using a parameterized query."""
    now = str(datetime.datetime.now())
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in errors.items()],
    )
    conn.commit()


def store_api_metrics(
    conn: sqlite3.Connection, api_latency: dict[str, float]
) -> None:
    """Insert API latency averages using a parameterized query."""
    now = str(datetime.datetime.now())
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in api_latency.items()],
    )
    conn.commit()


def build_html_report(
    errors: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: int,
) -> str:
    """Assemble the HTML report string."""
    rows: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in errors.items():
        rows.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    rows += ["</ul>", "<h2>API Latency</h2>", "<table border='1'>",
             "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"]
    for ep, avg in api_latency.items():
        rows.append(f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>")
    rows += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    return "\n".join(rows)


def write_report(html: str, filepath: str = "report.html") -> None:
    """Write the HTML report to *filepath*."""
    with open(filepath, "w") as f:
        f.write(html)


def _write_sample_data(filepath: str) -> None:
    """Write sample log data when the log file does not exist."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(filepath, "w") as f:
        for line in lines:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    config = load_config()

    if not os.path.exists(config.log_file):
        _write_sample_data(config.log_file)

    # Extract
    entries = extract_logs(config.log_file)
    print(f"Parsed {len(entries)} log entries from {config.log_file}")

    # Transform
    errors = aggregate_errors(entries)
    api_latency = compute_api_latency(entries)
    active_sessions = track_active_sessions(entries)

    # Load — database
    conn = init_database(config.db_path)
    store_errors(conn, errors)
    store_api_metrics(conn, api_latency)
    conn.close()

    # Load — report
    html = build_html_report(errors, api_latency, active_sessions)
    write_report(html)

    print(f"Report written to report.html — {len(errors)} error type(s), "
          f"{len(api_latency)} endpoint(s), "
          f"{active_sessions} active session(s)")


if __name__ == "__main__":
    main()
