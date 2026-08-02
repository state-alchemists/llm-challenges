"""
Pipeline for processing server logs and generating an HTML report.

Extracts log data, aggregates metrics, stores them in SQLite (using
parameterized queries), and produces a summary report.

Configuration (all via environment variables):
    DB_PATH     -- path to SQLite database (default: metrics.db)
    LOG_FILE    -- path to server log file (default: server.log)
    DB_HOST     -- database host (default: localhost)
    DB_PORT     -- database port (default: 5432)
    DB_USER     -- database user (default: admin)
    DB_PASS     -- database password (default: empty)
"""

import datetime
import os
import re
import sqlite3
from typing import TypedDict


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class LogEntry(TypedDict):
    """A log record with timestamp, level, and raw message."""
    timestamp: str
    level: str
    message: str


class APIRecord(TypedDict):
    """An API call record."""
    timestamp: str
    endpoint: str
    ms: int


class SessionRecord(TypedDict):
    """A user-session event record."""
    timestamp: str
    user_id: str
    action: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")

# Compiled regexes (module-level for efficiency)
_RE_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<rest>.*)$"
)

_RE_USER = re.compile(r"^User (?P<user_id>\S+) (?P<action>logged in|logged out)$")
_RE_API = re.compile(
    r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def extract(path: str) -> tuple[list[LogEntry], list[APIRecord], list[SessionRecord]]:
    """
    Parse the log file and return structured records.

    Args:
        path: Path to the server log file.

    Returns:
        A 3-tuple of (log_entries, api_records, session_records), each a list
        of TypedDicts described above.
    """
    log_entries: list[LogEntry] = []
    api_records: list[APIRecord] = []
    session_records: list[SessionRecord] = []

    if not os.path.exists(path):
        return log_entries, api_records, session_records

    with open(path, "r") as fh:
        for line in fh:
            m = _RE_LOG.match(line)
            if not m:
                continue

            ts = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                log_entries.append({"timestamp": ts, "level": level, "message": rest})

            elif level == "INFO":
                user_m = _RE_USER.match(rest)
                if user_m:
                    session_records.append({
                        "timestamp": ts,
                        "user_id": user_m.group("user_id"),
                        "action": user_m.group("action"),
                    })
                    log_entries.append({"timestamp": ts, "level": level, "message": rest})

                api_m = _RE_API.match(rest)
                if api_m:
                    api_records.append({
                        "timestamp": ts,
                        "endpoint": api_m.group("endpoint"),
                        "ms": int(api_m.group("ms")),
                    })

            elif level == "WARN":
                log_entries.append({"timestamp": ts, "level": level, "message": rest})

    return log_entries, api_records, session_records


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def transform(
    log_entries: list[LogEntry],
    api_records: list[APIRecord],
    session_records: list[SessionRecord],
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """
    Aggregate parsed records into the shapes needed for the report.

    Args:
        log_entries: Raw ERROR/WARN/INFO lines.
        api_records: API call timing records.
        session_records: User login/logout events.

    Returns:
        A 3-tuple of:
        - error_counts: error message -> occurrence count
        - api_latency: endpoint -> list of duration_ms values
        - active_sessions: number of currently logged-in users
    """
    # Error aggregation
    error_counts: dict[str, int] = {}
    for entry in log_entries:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    # API latency aggregation
    api_latency: dict[str, list[int]] = {}
    for rec in api_records:
        api_latency.setdefault(rec["endpoint"], []).append(rec["ms"])

    # Active-session tracking
    active_sessions = 0
    active_users: set[str] = set()
    for rec in sorted(session_records, key=lambda r: r["timestamp"]):
        if rec["action"] == "logged in":
            active_users.add(rec["user_id"])
        elif rec["action"] == "logged out":
            active_users.discard(rec["user_id"])
    active_sessions = len(active_users)

    return error_counts, api_latency, active_sessions


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """
    Write aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file (created if absent).
        error_counts: Error message -> count mapping.
        api_latency: Endpoint -> list of duration_ms values.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    # Parameterized inserts — no string formatting
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """
    Build the HTML report string.

    Args:
        error_counts: Error message -> count mapping.
        api_latency: Endpoint -> list of duration_ms values.
        active_sessions: Number of users currently logged in.

    Returns:
        Complete HTML document as a string.
    """
    out = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
    )

    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, times in api_latency.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline.

    Reads configuration from environment variables (with safe defaults),
    extracts and transforms log data, loads metrics into SQLite, and
    writes ``report.html`` to the working directory.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    log_entries, api_records, session_records = extract(LOG_FILE)

    error_counts, api_latency, active_sessions = transform(
        log_entries, api_records, session_records
    )

    load(DB_PATH, error_counts, api_latency)

    report_html = generate_report(error_counts, api_latency, active_sessions)
    with open("report.html", "w") as fh:
        fh.write(report_html)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        # Bootstrap a minimal log so the script is self-running
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
