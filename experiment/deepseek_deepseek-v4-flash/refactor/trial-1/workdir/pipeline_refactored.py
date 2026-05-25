"""Server log processing pipeline — Extract, Transform, Load.

Reads server logs, parses them with regex, computes error summaries,
API latency statistics, and active session counts, persists results
to SQLite, and generates an HTML report.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ===================================================================
# Configuration (loaded from environment variables)
# ===================================================================

@dataclass(frozen=True, slots=True)
class Config:
    """Application configuration loaded from environment variables.

    Every field has a default so the pipeline can run with no setup.
    """

    db_path: Path
    log_file_path: Path
    report_path: Path
    db_host: str
    db_port: int
    db_user: str
    db_password: str


def load_config() -> Config:
    """Read configuration from environment variables.

    Env vars (all optional, with sensible defaults):
        PIPELINE_DB_PATH          — SQLite database file path
        PIPELINE_LOG_FILE         — Server log file path
        PIPELINE_REPORT_PATH      — Output HTML report path
        PIPELINE_DB_HOST          — Database hostname (informational)
        PIPELINE_DB_PORT          — Database port (informational)
        PIPELINE_DB_USER          — Database user (informational)
        PIPELINE_DB_PASSWORD      — Database password (informational)

    Returns:
        Config populated from the environment.
    """
    return Config(
        db_path=Path(os.getenv("PIPELINE_DB_PATH", "metrics.db")),
        log_file_path=Path(os.getenv("PIPELINE_LOG_FILE", "server.log")),
        report_path=Path(os.getenv("PIPELINE_REPORT_PATH", "report.html")),
        db_host=os.getenv("PIPELINE_DB_HOST", "localhost"),
        db_port=int(os.getenv("PIPELINE_DB_PORT", "5432")),
        db_user=os.getenv("PIPELINE_DB_USER", "admin"),
        db_password=os.getenv("PIPELINE_DB_PASSWORD", "password123"),
    )


# ===================================================================
# Data types
# ===================================================================

@dataclass
class LogRecord:
    """A single parsed entry from the server log."""

    timestamp: str
    record_type: str  # "ERROR" | "WARN" | "USER" | "API"
    message: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None


# ===================================================================
# Regex patterns — compiled once at module load
# ===================================================================

# Pattern: 2024-01-01 12:05:00 ERROR Database timeout
_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.+)$"
)
# Pattern: 2024-01-01 12:09:00 WARN Memory usage at 87%
_RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.+)$"
)
# Pattern: 2024-01-01 12:00:00 INFO User 42 logged in
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User "
    r"(?P<user_id>\d+) (?P<action>.+)$"
)
# Pattern: 2024-01-01 12:08:00 INFO API /users/profile took 250ms
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API "
    r"(?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)


# ===================================================================
# Extract — read and parse the log file
# ===================================================================

def parse_log_line(line: str) -> Optional[LogRecord]:
    """Parse a single log line using compiled regex patterns.

    Tries API, User, ERROR, and WARN patterns in priority order.
    Returns None for lines that match none of the recognised formats.

    Args:
        line: A single line from the log file (trailing newline stripped).

    Returns:
        A LogRecord if the line matched a known pattern, else None.
    """
    line = line.rstrip("\n")

    m = _RE_API.match(line)
    if m:
        return LogRecord(
            timestamp=m.group("timestamp"),
            record_type="API",
            endpoint=m.group("endpoint"),
            duration_ms=int(m.group("duration")),
        )

    m = _RE_USER.match(line)
    if m:
        return LogRecord(
            timestamp=m.group("timestamp"),
            record_type="USER",
            user_id=m.group("user_id"),
            action=m.group("action"),
        )

    m = _RE_ERROR.match(line)
    if m:
        return LogRecord(
            timestamp=m.group("timestamp"),
            record_type="ERROR",
            message=m.group("message"),
        )

    m = _RE_WARN.match(line)
    if m:
        return LogRecord(
            timestamp=m.group("timestamp"),
            record_type="WARN",
            message=m.group("message"),
        )

    return None


def read_log_file(path: Path) -> List[LogRecord]:
    """Read and parse every line in the log file.

    Silently skips blank lines and unrecognised formats. Uses a context
    manager so the file handle is always closed.

    Args:
        path: Path to the server log file.

    Returns:
        List of successfully parsed LogRecord objects.
    """
    if not path.exists():
        return []

    records: List[LogRecord] = []
    with path.open("r") as f:
        for line in f:
            record = parse_log_line(line)
            if record is not None:
                records.append(record)
    return records


# ===================================================================
# Transform — derive statistics from parsed records
# ===================================================================

def count_errors(records: List[LogRecord]) -> Dict[str, int]:
    """Count occurrences of each distinct error message.

    Args:
        records: All parsed log records from the log file.

    Returns:
        Mapping of error message text → total occurrence count.
    """
    counts: Dict[str, int] = {}
    for rec in records:
        if rec.record_type == "ERROR" and rec.message is not None:
            counts[rec.message] = counts.get(rec.message, 0) + 1
    return counts


def compute_api_latency(records: List[LogRecord]) -> Dict[str, float]:
    """Compute average latency (in milliseconds) per API endpoint.

    Args:
        records: All parsed log records from the log file.

    Returns:
        Mapping of endpoint path → average response time in ms.
    """
    values: Dict[str, List[int]] = {}
    for rec in records:
        if rec.record_type == "API" and rec.endpoint is not None and rec.duration_ms is not None:
            values.setdefault(rec.endpoint, []).append(rec.duration_ms)

    return {ep: sum(times) / len(times) for ep, times in values.items()}


def track_active_sessions(records: List[LogRecord]) -> int:
    """Replay login/logout events and return the final active session count.

    A user is considered active from the moment they log in until they
    log out. If a user logs out without a prior login event they are
    ignored.

    Args:
        records: All parsed log records from the log file.

    Returns:
        Number of users still active at the end of the log.
    """
    sessions: Dict[str, str] = {}
    for rec in records:
        if rec.record_type != "USER" or rec.user_id is None or rec.action is None:
            continue
        if "logged in" in rec.action:
            sessions[rec.user_id] = rec.timestamp
        elif "logged out" in rec.action and rec.user_id in sessions:
            del sessions[rec.user_id]
    return len(sessions)


# ===================================================================
# Load — persist to SQLite and generate the HTML report
# ===================================================================

def init_database(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and initialise schema.

    Creates the ``errors`` and ``api_metrics`` tables if they do not
    already exist. Enables WAL mode for better concurrent reads.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open database connection in WAL mode.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors ("
        "  dt TEXT NOT NULL,"
        "  message TEXT NOT NULL,"
        "  count INTEGER NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics ("
        "  dt TEXT NOT NULL,"
        "  endpoint TEXT NOT NULL,"
        "  avg_ms REAL NOT NULL"
        ")"
    )
    return conn


def insert_error_summary(
    conn: sqlite3.Connection,
    error_counts: Dict[str, int],
    timestamp: str,
) -> None:
    """Write error summary rows using a parameterised query.

    Uses ``?`` placeholders to prevent SQL injection.

    Args:
        conn: Open database connection.
        error_counts: Error message → occurrence count mapping.
        timestamp: ISO-formatted timestamp to tag each row with.
    """
    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (timestamp, msg, count),
        )


def insert_api_metrics(
    conn: sqlite3.Connection,
    api_stats: Dict[str, float],
    timestamp: str,
) -> None:
    """Write API latency rows using a parameterised query.

    Uses ``?`` placeholders to prevent SQL injection.

    Args:
        conn: Open database connection.
        api_stats: Endpoint → average latency (ms) mapping.
        timestamp: ISO-formatted timestamp to tag each row with.
    """
    for ep, avg in api_stats.items():
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (timestamp, ep, avg),
        )


def generate_html_report(
    error_counts: Dict[str, int],
    api_stats: Dict[str, float],
    active_sessions: int,
) -> str:
    """Build the HTML report as a string.

    Sections produced:
        - Error Summary (bullet list)
        - API Latency (table with border)
        - Active Sessions (count)

    Args:
        error_counts: Error message → occurrence count.
        api_stats: Endpoint → average latency in ms.
        active_sessions: Number of currently active user sessions.

    Returns:
        Complete HTML document as a string.
    """
    parts = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        parts.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    parts += [
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for ep, avg in api_stats.items():
        parts.append(f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>")
    parts += [
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


def write_report(html: str, path: Path) -> None:
    """Persist the HTML report to disk.

    Args:
        html: Complete HTML document string.
        path: Destination file path (parent directories must exist).
    """
    path.write_text(html)


# ===================================================================
# Pipeline orchestration
# ===================================================================

def run_pipeline(cfg: Config) -> None:
    """Execute the full ETL pipeline.

    Steps:
        1. Log a connection banner (informational only).
        2. Extract: read and parse every line from the log file.
        3. Transform: compute error counts, API latency, and sessions.
        4. Load: persist statistics to SQLite, then write the HTML report.

    Args:
        cfg: Application configuration loaded from the environment.
    """
    print(f"Connecting to {cfg.db_host}:{cfg.db_port} as {cfg.db_user}...")

    records = read_log_file(cfg.log_file_path)
    error_counts = count_errors(records)
    api_stats = compute_api_latency(records)
    active_sessions = track_active_sessions(records)

    now = datetime.now().isoformat()

    conn = init_database(cfg.db_path)
    try:
        insert_error_summary(conn, error_counts, now)
        insert_api_metrics(conn, api_stats, now)
        conn.commit()
    finally:
        conn.close()

    html = generate_html_report(error_counts, api_stats, active_sessions)
    write_report(html, cfg.report_path)

    print(f"Job finished at {datetime.now()}")


def _write_demo_log(path: Path) -> None:
    """Write a sample log file so the pipeline can run without real data."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    cfg = load_config()
    if not cfg.log_file_path.exists():
        _write_demo_log(cfg.log_file_path)
    run_pipeline(cfg)
