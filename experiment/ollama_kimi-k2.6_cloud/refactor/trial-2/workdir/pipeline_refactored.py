"""Server log ETL pipeline.

Reads structured server logs, aggregates error counts and API latency metrics,
persists them to SQLite, and writes an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional, Tuple


class ParsedRecord(NamedTuple):
    """A single parsed log record."""

    dt: str
    level: str
    message: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Configuration (loaded from environment)
# ---------------------------------------------------------------------------
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_PATH = os.getenv("DB_PATH", "metrics.db")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
_LOG_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<lvl>\w+) "
    r"(?P<rest>.*)$"
)
_USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<dur>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def extract(log_path: str) -> List[ParsedRecord]:
    """Read *log_path* and parse each line into a structured record.

    Args:
        log_path: Path to the server log file.

    Returns:
        A list of :class:`ParsedRecord` objects.
    """
    records: List[ParsedRecord] = []
    if not os.path.exists(log_path):
        return records

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            match = _LOG_RE.match(line)
            if not match:
                continue

            dt = match.group("dt")
            lvl = match.group("lvl")
            rest = match.group("rest")

            if lvl == "ERROR":
                records.append(ParsedRecord(dt=dt, level=lvl, message=rest))
            elif lvl == "WARN":
                records.append(ParsedRecord(dt=dt, level=lvl, message=rest))
            elif lvl == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    records.append(
                        ParsedRecord(
                            dt=dt,
                            level=lvl,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                else:
                    api_match = _API_RE.match(rest)
                    if api_match:
                        dur_str = api_match.group("dur")
                        records.append(
                            ParsedRecord(
                                dt=dt,
                                level=lvl,
                                endpoint=api_match.group("endpoint"),
                                duration_ms=int(dur_str) if dur_str is not None else 0,
                            )
                        )
    return records


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
def transform(
    records: List[ParsedRecord],
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Aggregate parsed records into summary statistics.

    Args:
        records: Parsed log records from :func:`extract`.

    Returns:
        A three-tuple of:
        - ``error_counts``: mapping of error message -> occurrence count.
        - ``api_stats``: mapping of endpoint -> list of latency values in ms.
        - ``sessions``: mapping of user_id -> login datetime for active sessions.
    """
    error_counts: Dict[str, int] = defaultdict(int)
    api_stats: Dict[str, List[int]] = defaultdict(list)
    sessions: Dict[str, str] = {}

    for rec in records:
        if rec.level == "ERROR":
            if rec.message is not None:
                error_counts[rec.message] += 1
        elif rec.level == "WARN":
            # WARN records are parsed but not surfaced in the current report.
            pass
        elif rec.level == "INFO":
            if rec.user_id is not None and rec.action is not None:
                uid = rec.user_id
                action = rec.action
                if "logged in" in action:
                    sessions[uid] = rec.dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
            elif rec.endpoint is not None:
                api_stats[rec.endpoint].append(rec.duration_ms or 0)

    return dict(error_counts), dict(api_stats), sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _init_db(conn: sqlite3.Connection) -> None:
    """Create the required tables if they do not already exist."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
        """
    )
    conn.commit()


def _persist_metrics(
    conn: sqlite3.Connection,
    error_counts: Dict[str, int],
    api_stats: Dict[str, List[int]],
) -> None:
    """Insert aggregated metrics using parameterized queries."""
    cur = conn.cursor()
    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_stats.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()


def _generate_report(
    error_counts: Dict[str, int],
    api_stats: Dict[str, List[int]],
    sessions: Dict[str, str],
) -> str:
    """Build the HTML report string.

    Args:
        error_counts: Aggregated error occurrences.
        api_stats: Aggregated API latency measurements.
        sessions: Currently active user sessions.

    Returns:
        A complete HTML document.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>", "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])
    for ep, times in api_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{len(sessions)} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines)


def load(
    error_counts: Dict[str, int],
    api_stats: Dict[str, List[int]],
    sessions: Dict[str, str],
    db_path: str,
) -> None:
    """Persist aggregates to SQLite and write *report.html*.

    Args:
        error_counts: Aggregated error occurrences.
        api_stats: Aggregated API latency measurements.
        sessions: Currently active user sessions.
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        _persist_metrics(conn, error_counts, api_stats)
    finally:
        conn.close()

    report = _generate_report(error_counts, api_stats, sessions)
    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _seed_demo_log(log_path: str) -> None:
    """Write a small sample log so the pipeline has data to process."""
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


def main() -> None:
    """Entry point: seed demo data if missing, then run ETL."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    if not os.path.exists(LOG_FILE):
        _seed_demo_log(LOG_FILE)

    records = extract(LOG_FILE)
    error_counts, api_stats, sessions = transform(records)
    load(error_counts, api_stats, sessions, DB_PATH)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
