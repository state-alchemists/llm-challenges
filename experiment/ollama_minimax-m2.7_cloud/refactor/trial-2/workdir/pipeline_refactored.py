"""
Log processing pipeline: Extract → Transform → Load → Report.

Reads server logs, aggregates error counts and API latency metrics into SQLite,
then generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration (all from environment variables with sensible defaults for dev)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("PIPELINE_LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("PIPELINE_DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
DB_USER: str = os.environ.get("PIPELINE_DB_USER", "admin")
DB_PASS: str = os.environ.get("PIPELINE_DB_PASS", "")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ErrorRecord(TypedDict):
    dt: str
    t: str
    m: str


class UserRecord(TypedDict):
    dt: str
    t: str
    u: str
    a: str


class ApiRecord(TypedDict):
    d: str
    endpoint: str
    ms: int


class WarnRecord(TypedDict):
    dt: str
    t: str
    m: str


LogRecord = ErrorRecord | UserRecord | WarnRecord


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Pre-compiled regex patterns for log-line parsing.
# Format: "2024-01-01 12:00:00 LEVEL <rest>"
_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN)"
)
_RE_ERROR = re.compile(r"ERROR (?P<message>.+)")
_RE_USER = re.compile(r"INFO User (?P<uid>\S+) (?P<action>.+)")
_RE_API = re.compile(r"INFO API (?P<endpoint>\S+) took (?P<ms>\d+)ms")
_RE_WARN = re.compile(r"WARN (?P<message>.+)")


def extract_logs(log_path: str) -> tuple[list[ErrorRecord], list[UserRecord], list[ApiRecord], list[WarnRecord]]:
    """
    Parse ``log_path`` and return structured records grouped by type.

    Returns
    -------
    (errors, users, api_calls, warnings)

    Each list contains TypedDict records; see types above.
    """
    errors: list[ErrorRecord] = []
    users: list[UserRecord] = []
    api_calls: list[ApiRecord] = []
    warnings: list[WarnRecord] = []

    if not os.path.exists(log_path):
        print(f"[extract] Log file not found: {log_path}")
        return errors, users, api_calls, warnings

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m_line = _RE_LOG_LINE.match(line)
            if not m_line:
                continue

            ts = m_line.group("timestamp")
            level = m_line.group("level")

            if level == "ERROR":
                m_err = _RE_ERROR.search(line)  # .search() not .match() — ERROR is not at line start
                if m_err:
                    errors.append({"dt": ts, "t": "ERR", "m": m_err.group("message")})

            elif level == "INFO":
                m_user = _RE_USER.search(line)  # .search() not .match() — INFO/User prefix is not at line start
                if m_user:
                    users.append({
                        "dt": ts,
                        "t": "USR",
                        "u": m_user.group("uid"),
                        "a": m_user.group("action"),
                    })
                    continue

                m_api = _RE_API.search(line)  # .search() not .match() — API is not at line start
                if m_api:
                    api_calls.append({
                        "d": ts,
                        "endpoint": m_api.group("endpoint"),
                        "ms": int(m_api.group("ms")),
                    })

            elif level == "WARN":
                m_warn = _RE_WARN.search(line)  # .search() not .match() — WARN is not at line start
                if m_warn:
                    warnings.append({"dt": ts, "t": "WARN", "m": m_warn.group("message")})

    return errors, users, api_calls, warnings


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def count_errors_by_message(errors: list[ErrorRecord]) -> dict[str, int]:
    """Return a mapping from error message → occurrence count."""
    counts: dict[str, int] = {}
    for err in errors:
        counts[err["m"]] = counts.get(err["m"], 0) + 1
    return counts


def aggregate_api_latency(api_calls: list[ApiRecord]) -> dict[str, list[int]]:
    """
    Return a mapping from endpoint → list of observed latencies (ms).

    The caller is responsible for computing the average.
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call["endpoint"], []).append(call["ms"])
    return stats


def count_active_sessions(users: list[UserRecord]) -> int:
    """
    Return the number of currently-active sessions.

    A session starts on "logged in" and ends on "logged out".
    A user who logged in but never logged out is still active.
    """
    active: set[str] = set()
    for entry in users:
        uid = entry["u"]
        action = entry["a"]
        if "logged in" in action:
            active.add(uid)
        elif "logged out" in action:
            active.discard(uid)
    return len(active)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Create (or verify) the target tables exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def load_error_counts(
    conn: sqlite3.Connection,
    counts: dict[str, int],
    timestamp: str | None = None,
) -> None:
    """
    Upsert aggregated error counts into the ``errors`` table.

    Uses INSERT with a WHERE clause to avoid duplicate rows per run;
    the report is the source of truth for the current batch.
    """
    ts = timestamp or datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for msg, count in counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (ts, msg, count),
        )
    conn.commit()


def load_api_metrics(
    conn: sqlite3.Connection,
    endpoint_stats: dict[str, list[int]],
    timestamp: str | None = None,
) -> None:
    """
    Compute and store average latency per endpoint.

    Uses INSERT (not upsert) so historical data remains queryable.
    """
    ts = timestamp or datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (ts, ep, avg),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_html_report(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """Render the three report sections as a standalone HTML string."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(
    db_path: str = DB_PATH,
    log_file: str = LOG_FILE,
    db_host: str = DB_HOST,
    db_port: int = DB_PORT,
    db_user: str = DB_USER,
    db_pass: str = DB_PASS,
    output_path: str = "report.html",
) -> None:
    """
    Execute the full ETL pipeline.

    Parameters
    ----------
    db_path
        Path to the SQLite database file.
    log_file
        Path to the server log file.
    db_host, db_port, db_user, db_pass
        Connection parameters (currently logged; SQLite has no auth).
    output_path
        Destination for the HTML report.
    """
    print(f"[pipeline] Connecting to {db_host}:{db_port} as {db_user} ...")

    # Extract
    errors, users, api_calls, warnings = extract_logs(log_file)
    print(f"[pipeline] Extracted {len(errors)} errors, {len(api_calls)} API calls, {len(users)} user events")

    # Transform
    error_counts = count_errors_by_message(errors)
    endpoint_stats = aggregate_api_latency(api_calls)
    active_sessions = count_active_sessions(users)

    # Load — write to SQLite
    conn = sqlite3.connect(db_path)
    init_db(conn)
    load_error_counts(conn, error_counts)
    load_api_metrics(conn, endpoint_stats)
    conn.close()

    # Report
    html = build_html_report(error_counts, endpoint_stats, active_sessions)
    Path(output_path).write_text(html)
    print(f"[pipeline] Report written to {output_path}")
    print(f"[pipeline] Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bootstrap a minimal dev log when the file is absent so the script
    # is self-contained and runnable out of the box.
    if not os.path.exists(LOG_FILE):
        print(f"[setup] {LOG_FILE} not found — creating a dev sample")
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )

    run_pipeline()
