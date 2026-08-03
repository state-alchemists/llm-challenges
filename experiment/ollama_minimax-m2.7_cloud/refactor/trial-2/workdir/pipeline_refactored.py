"""
Log processing pipeline that extracts metrics from server logs and generates an HTML report.

Architecture follows the ETL (Extract → Transform → Load) pattern:
    - Extract:  parse raw log lines into structured records
    - Transform: aggregate records into error counts, API latency stats, session state
    - Load:      write results to SQLite and produce an HTML report

All configuration is driven by environment variables; no credentials or paths are
hardcoded in this module.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# Configuration — read once at startup so the entire module is auditable
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")  # empty default; set via env


# ---------------------------------------------------------------------------
# Log line regexes (pre-compiled for performance)
# ---------------------------------------------------------------------------

_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<rest>.+)$"
)

# INFO with User activity
_RE_USER_ACTION = re.compile(
    r"^User (?P<uid>\S+) (?P<action>logged in|logged out|.+)$"
)

# INFO with API call
_RE_API_CALL = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT — parse raw log lines into typed records
# ---------------------------------------------------------------------------

ErrorRecord = dict[str, Any]      # keys: "timestamp", "message"
UserRecord = dict[str, Any]       # keys: "timestamp", "uid", "action"
ApiRecord  = dict[str, Any]       # keys: "timestamp", "endpoint", "ms"
WarnRecord = dict[str, Any]       # keys: "timestamp", "message"


def extract_log_records(log_path: str) -> tuple[
    list[ErrorRecord],
    list[UserRecord],
    list[ApiRecord],
    list[WarnRecord],
]:
    """
    Parse ``log_path`` and return four typed lists.

    Returns
    -------
    (errors, users, api_calls, warnings)
        Each list contains records of that log level / category.

    Raises
    ------
    FileNotFoundError
        If the log file does not exist.
    """
    errors: list[ErrorRecord] = []
    users: list[UserRecord] = []
    api_calls: list[ApiRecord] = []
    warnings: list[WarnRecord] = []

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            m = _RE_LOG_LINE.match(line)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                errors.append(ErrorRecord(timestamp=timestamp, message=rest))

            elif level == "INFO":
                um = _RE_USER_ACTION.match(rest)
                if um:
                    users.append(UserRecord(
                        timestamp=timestamp,
                        uid=um.group("uid"),
                        action=um.group("action"),
                    ))
                    continue

                am = _RE_API_CALL.match(rest)
                if am:
                    api_calls.append(ApiRecord(
                        timestamp=timestamp,
                        endpoint=am.group("endpoint"),
                        ms=int(am.group("ms")),
                    ))
                    continue

            elif level == "WARN":
                warnings.append(WarnRecord(timestamp=timestamp, message=rest))

    return errors, users, api_calls, warnings


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate records into report-ready data structures
# ---------------------------------------------------------------------------

def transform_errors(errors: list[ErrorRecord]) -> dict[str, int]:
    """
    Count how many times each unique error message appears.

    Returns
    -------
    dict[str, int]
        Mapping of error message → occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        msg = err["message"]
        counts[msg] = counts.get(msg, 0) + 1
    return counts


def transform_api_latency(api_calls: list[ApiRecord]) -> dict[str, list[int]]:
    """
    Group API calls by endpoint and collect their latencies.

    Returns
    -------
    dict[str, list[int]]
        Mapping of endpoint → list of observed latencies in ms.
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        stats.setdefault(ep, []).append(call["ms"])
    return stats


def transform_active_sessions(users: list[UserRecord]) -> int:
    """
    Derive the number of currently active sessions.

    A session starts on ``logged in`` and ends on ``logged out``.
    Users who logged in but never logged out are considered still active.

    Returns
    -------
    int
        Number of users with an open session.
    """
    active: dict[str, str] = {}  # uid → timestamp of login
    for u in users:
        if u["action"] == "logged in":
            active[u["uid"]] = u["timestamp"]
        elif u["action"] == "logged out":
            active.pop(u["uid"], None)
    return len(active)


# ---------------------------------------------------------------------------
# LOAD — write aggregated data to SQLite and produce the HTML report
# ---------------------------------------------------------------------------

def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create (or verify) the two metric tables."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def _load_errors(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Insert error summary rows using a **parameterized** query.

    Parameters
    ----------
    conn
        Live SQLite connection.
    error_counts
        Error message → count mapping from ``transform_errors``.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    # ✅ Parameterized — no string formatting, no injection risk
    cur.executemany(
        "INSERT INTO errors VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in error_counts.items()],
    )
    conn.commit()


def _load_api_metrics(
    conn: sqlite3.Connection, api_stats: dict[str, list[int]]
) -> None:
    """
    Insert per-endpoint average latency rows using a **parameterized** query.

    Parameters
    ----------
    conn
        Live SQLite connection.
    api_stats
        Endpoint → latency list mapping from ``transform_api_latency``.
    """
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    rows = [
        (now, ep, sum(times) / len(times))
        for ep, times in api_stats.items()
    ]
    # ✅ Parameterized
    cur.executemany(
        "INSERT INTO api_metrics VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def load_to_sqlite(
    db_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """
    Persist error summaries and API latency aggregates to the SQLite database.

    Parameters
    ----------
    db_path
        Path to the SQLite database file.
    error_counts
        Error message → count mapping.
    api_stats
        Endpoint → latency list mapping.
    """
    conn = sqlite3.connect(db_path)
    try:
        _ensure_tables(conn)
        _load_errors(conn, error_counts)
        _load_api_metrics(conn, api_stats)
    finally:
        conn.close()


def load_to_html(
    output_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """
    Write the HTML report covering errors, API latency, and active sessions.

    Parameters
    ----------
    output_path
        Destination file path for the HTML report.
    error_counts
        Error message → count mapping.
    api_stats
        Endpoint → latency list mapping.
    active_sessions
        Current count of open user sessions.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        # Escape HTML special chars to prevent XSS in the report itself
        safe_msg = (
            err_msg.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
        )
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, times in api_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body></html>")

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    log_path: str = LOG_FILE,
    db_path: str = DB_PATH,
    report_path: str = "report.html",
) -> None:
    """
    Run the full ETL pipeline.

    Parameters
    ----------
    log_path
        Path to the server log file.
    db_path
        Path to the SQLite database file.
    report_path
        Destination for the HTML report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    errors, users, api_calls, _warnings = extract_log_records(log_path)

    # Transform
    error_counts = transform_errors(errors)
    api_stats = transform_api_latency(api_calls)
    active_sessions = transform_active_sessions(users)

    # Load
    load_to_sqlite(db_path, error_counts, api_stats)
    load_to_html(report_path, error_counts, api_stats, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Bootstrap — create a sample log if none exists so the script is runnable
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(LOG_FILE, "w") as fh:
            fh.write("\n".join(sample_lines) + "\n")

    run_pipeline()
