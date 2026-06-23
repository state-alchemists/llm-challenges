"""Server-log processing pipeline — extract, transform, load.

Reads a structured server log, parses ERROR / WARN / User-action / API-call
events, aggregates them, persists results to SQLite (parameterised queries),
and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration — loaded from environment variables
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ["DB_USER"]        # no default — must be set
DB_PASS = os.environ["DB_PASS"]        # no default — must be set


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class LogRecord:
    """A single parsed log entry.

    Attributes:
        timestamp:  When the event was logged (``%Y-%m-%d %H:%M:%S``).
        level:      Severity — ``"ERROR"``, ``"WARN"``, or ``"INFO"``.
        message:    Error or warning body text.
        user_id:    User ID when the line describes a user action.
        action:     Description of the user action (e.g.  ``"logged in"``).
        endpoint:   API endpoint path (e.g. ``"/users/profile"``).
        duration_ms: API call duration in milliseconds.
    """
    timestamp: datetime.datetime
    level: str
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Regex patterns (compiled once at module load)
# ---------------------------------------------------------------------------

_LOG_HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.+)$",
)

_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")

_API_RE = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<dms>\d+)ms)?$",
)


# ===== EXTRACT =============================================================

def parse_log_line(line: str) -> Optional[LogRecord]:
    """Parse a single server-log line into a :class:`LogRecord`.

    Recognised line formats::

        <ts> ERROR <message>
        <ts> WARN <message>
        <ts> INFO User <id> logged in|out
        <ts> INFO API <endpoint> took <ms>ms

    Returns ``None`` for blank lines or unrecognised INFO subtypes
    (matching the original script's behaviour).
    """
    line = line.strip()
    if not line:
        return None

    m = _LOG_HEADER_RE.match(line)
    if not m:
        return None

    ts = datetime.datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
    level = m.group("level")
    rest = m.group("rest")

    if level in ("ERROR", "WARN"):
        return LogRecord(timestamp=ts, level=level, message=rest)

    # INFO — disambiguate User-action from API-call
    um = _USER_RE.match(rest)
    if um:
        return LogRecord(
            timestamp=ts,
            level=level,
            user_id=um.group("uid"),
            action=um.group("action"),
        )

    am = _API_RE.match(rest)
    if am:
        dms_str = am.group("dms")
        return LogRecord(
            timestamp=ts,
            level=level,
            endpoint=am.group("endpoint"),
            duration_ms=int(dms_str) if dms_str else None,
        )

    # Unhandled INFO — ignore
    return None


def extract_logs(log_path: Path) -> list[LogRecord]:
    """Read *every* line of *log_path* and return all parseable records.

    Blank lines and unrecognised formats are silently skipped.
    """
    if not log_path.is_file():
        return []

    records: list[LogRecord] = []
    with log_path.open("r") as f:
        for line in f:
            rec = parse_log_line(line)
            if rec is not None:
                records.append(rec)
    return records


# ===== TRANSFORM ===========================================================

def summarize_errors(records: list[LogRecord]) -> dict[str, int]:
    """Count occurrences of each distinct ERROR message."""
    counts: dict[str, int] = {}
    for rec in records:
        if rec.level == "ERROR" and rec.message is not None:
            counts[rec.message] = counts.get(rec.message, 0) + 1
    return counts


def compute_api_averages(records: list[LogRecord]) -> dict[str, float]:
    """Compute mean API latency (ms) grouped by endpoint."""
    raw: dict[str, list[int]] = {}
    for rec in records:
        if rec.endpoint is not None and rec.duration_ms is not None:
            raw.setdefault(rec.endpoint, []).append(rec.duration_ms)

    return {
        ep: sum(times) / len(times)
        for ep, times in raw.items()
    }


def track_active_sessions(records: list[LogRecord]) -> set[str]:
    """Return user IDs that have logged in but not yet logged out."""
    active: set[str] = set()
    for rec in records:
        if rec.action is None or rec.user_id is None:
            continue
        if "logged in" in rec.action:
            active.add(rec.user_id)
        elif "logged out" in rec.action and rec.user_id in active:
            active.remove(rec.user_id)
    return active


# ===== LOAD ================================================================

def init_db(db_path: str) -> sqlite3.Connection:
    """Open and return a connection to the SQLite database.

    Creates the ``errors`` and ``api_metrics`` tables if they do not exist.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)",
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)",
    )
    conn.commit()
    return conn


def persist_error_summary(
    conn: sqlite3.Connection, summary: dict[str, int],
) -> None:
    """Insert error counts into the ``errors`` table.

    Uses parameterised queries (``?`` placeholders) to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in summary.items()],
    )
    conn.commit()


def persist_api_metrics(
    conn: sqlite3.Connection, averages: dict[str, float],
) -> None:
    """Insert average API latencies into the ``api_metrics`` table.

    Uses parameterised queries (``?`` placeholders) to prevent SQL injection.
    """
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in averages.items()],
    )
    conn.commit()


def generate_html_report(
    error_summary: dict[str, int],
    api_averages: dict[str, float],
    active_session_count: int,
) -> str:
    """Build the complete HTML report string.

    The report contains three sections in order:
        1. Error summary (unordered list)
        2. API latency  (table)
        3. Active sessions (simple count)
    """
    parts: list[str] = []
    parts.append("<!DOCTYPE html>\n<html>\n<head><title>System Report</title></head>\n<body>")

    # 1. Error summary
    parts.append("<h1>Error Summary</h1>\n<ul>")
    for err_msg, count in error_summary.items():
        parts.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>",
        )
    parts.append("</ul>")

    # 2. API latency table
    parts.append("<h2>API Latency</h2>\n<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in api_averages.items():
        parts.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    parts.append("</table>")

    # 3. Active sessions
    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{active_session_count} user(s) currently active</p>")

    parts.append("</body>\n</html>")
    return "\n".join(parts)


def write_report(html: str, output_path: str) -> None:
    """Write *html* to *output_path*."""
    Path(output_path).write_text(html)


# ===== PIPELINE ORCHESTRATOR ===============================================

def run_pipeline(
    log_path: str = LOG_FILE,
    db_path: str = DB_PATH,
    report_path: str = "report.html",
) -> None:
    """Execute the complete ETL pipeline: extract → transform → load.

    Args:
        log_path:   Path to the server log file.
        db_path:    Path to the SQLite database file.
        report_path: Path for the generated HTML report.
    """
    # --- Extract ---
    print(f"Parsing log file: {log_path}")
    records = extract_logs(Path(log_path))
    print(f"  Parsed {len(records)} record(s)")

    # --- Transform ---
    error_summary = summarize_errors(records)
    api_averages = compute_api_averages(records)
    active_sessions = track_active_sessions(records)

    print(f"  Errors: {len(error_summary)} unique message(s)")
    print(f"  API endpoints: {len(api_averages)}")
    print(f"  Active sessions: {len(active_sessions)}")

    # --- Load: database ---
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = init_db(db_path)
    persist_error_summary(conn, error_summary)
    persist_api_metrics(conn, api_averages)
    conn.close()

    # --- Load: report ---
    html = generate_html_report(
        error_summary, api_averages, len(active_sessions),
    )
    write_report(html, report_path)

    print(f"Report written to: {report_path}")
    print(f"Job finished at {datetime.datetime.now()}")


# ===== MAIN ================================================================

if __name__ == "__main__":
    # Create a sample log file if none exists (preserves original behaviour).
    log = Path(LOG_FILE)
    if not log.is_file():
        log.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
    run_pipeline()
