"""
Pipeline for processing server logs and generating an HTML report.

Extracts log entries, aggregates error counts and API latency metrics,
stores results in SQLite, and produces a report.
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import TypedDict


# Typed structures for clarity and type safety
class LogEntry(TypedDict):
    """A parsed log line for non-API/INFO events."""

    timestamp: str
    level: str
    message: str


class APIStat(TypedDict):
    """A single API call record."""

    endpoint: str
    ms: int


# ----------------------------------------------------------------------
# Configuration (all loaded from environment variables)
# ----------------------------------------------------------------------
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("REPORT_FILE", "report.html")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# ----------------------------------------------------------------------
# Log parsing
# ----------------------------------------------------------------------
# Matches: "2024-01-01 12:00:00 INFO User 42 logged in"
# Groups: timestamp, level, message
_LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)\s+(.*)$")

# Matches: "User 42 logged in" / "User 42 logged out"
_USER_PATTERN = re.compile(r"^User (\S+) (logged (?:in|out))$")

# Matches: "API /users/profile took 250ms"
_API_PATTERN = re.compile(r"API (\S+) took (\d+)ms")


def parse_log_entry(line: str, sessions: dict[str, str]) -> tuple[LogEntry | None, dict[str, str], APIStat | None]:
    """
    Parse a single log line using regex into structured data.

    Modifies ``sessions`` in-place when a user login/logout event is detected.

    Args:
        line: Raw log line from the log file.
        sessions: Active session map (uid -> login timestamp).

    Returns:
        A 3-tuple of (diagnostic_entry, updated_sessions, api_stat).
        ``diagnostic_entry`` is set for ERROR and WARN lines;
        ``api_stat`` is set for API lines; at least one caller of the
        return values is always non-None.
    """
    match = _LOG_PATTERN.match(line)
    if not match or match.lastindex < 3:
        return None, sessions, None

    timestamp, level, message = match.groups()
    log_entry: LogEntry = {"timestamp": timestamp, "level": level, "message": message.strip()}

    if log_entry["level"] == "ERROR":
        return log_entry, sessions, None

    if log_entry["level"] == "INFO":
        user_match = _USER_PATTERN.match(log_entry["message"])
        if user_match:
            uid = user_match.group(1)
            action = user_match.group(2)
            if action == "logged in":
                sessions[uid] = timestamp
            elif action == "logged out" and uid in sessions:
                sessions.pop(uid)
            return log_entry, sessions, None

        api_match = _API_PATTERN.search(log_entry["message"])
        if api_match:
            api_stat: APIStat = {"endpoint": api_match.group(1), "ms": int(api_match.group(2))}
            return None, sessions, api_stat

        return None, sessions, None

    if log_entry["level"] == "WARN":
        return log_entry, sessions, None

    return None, sessions, None


# ----------------------------------------------------------------------
# EXTRACT phase
# ----------------------------------------------------------------------
def extract(log_path: str) -> tuple[list[LogEntry], dict[str, str], list[APIStat]]:
    """
    Read and parse every line in the log file.

    Args:
        log_path: Path to the server log file.

    Returns:
        A 3-tuple of (diagnostic_entries, active_sessions, api_stats).
    """
    diagnostics: list[LogEntry] = []
    sessions: dict[str, str] = {}
    api_stats: list[APIStat] = []

    if not os.path.exists(log_path):
        print(f"[extract] Log file not found: {log_path}")
        return diagnostics, sessions, api_stats

    with open(log_path, "r") as f:
        for line in f:
            diag, sessions, api_stat = parse_log_entry(line, sessions)
            if diag is not None:
                diagnostics.append(diag)
            if api_stat is not None:
                api_stats.append(api_stat)

    return diagnostics, sessions, api_stats


# ----------------------------------------------------------------------
# TRANSFORM phase
# ----------------------------------------------------------------------
def transform(
    diagnostics: list[LogEntry], api_stats: list[APIStat]
) -> tuple[dict[str, int], dict[str, list[int]]]:
    """
    Aggregate raw parsed data into summary statistics.

    Args:
        diagnostics: ERROR and WARN log entries.
        api_stats: Individual API call records.

    Returns:
        A 2-tuple of (error_counts, api_latencies) where:
        - error_counts: error message -> occurrence count
        - api_latencies: endpoint -> list of latency values (ms)
    """
    error_counts: dict[str, int] = {}
    for entry in diagnostics:
        if entry["level"] == "ERROR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    api_latencies: dict[str, list[int]] = {}
    for stat in api_stats:
        api_latencies.setdefault(stat["endpoint"], []).append(stat["ms"])

    return error_counts, api_latencies


# ----------------------------------------------------------------------
# LOAD phase
# ----------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    """Create the metrics tables if they do not exist."""
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


def load(conn: sqlite3.Connection, error_counts: dict[str, int], api_latencies: dict[str, list[int]]) -> None:
    """
    Write aggregated data into SQLite using parameterized queries.

    Args:
        conn: Open SQLite connection.
        error_counts: Aggregated error message counts.
        api_latencies: Per-endpoint latency lists keyed by endpoint.
    """
    init_db(conn)
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()

    # Clear previous runs for this timestamp to allow re-running
    cur.execute("DELETE FROM errors WHERE dt = ?", (now,))
    cur.execute("DELETE FROM api_metrics WHERE dt = ?", (now,))

    # Parameterized inserts — no string formatting
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in api_latencies.items():
        avg_ms = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()


# ----------------------------------------------------------------------
# REPORT phase
# ----------------------------------------------------------------------
def generate_report(
    error_counts: dict[str, int],
    api_latencies: dict[str, list[int]],
    active_session_count: int,
    output_path: str,
) -> None:
    """
    Write the HTML report to disk.

    Args:
        error_counts: Error message -> count map.
        api_latencies: Endpoint -> latency list map.
        active_session_count: Number of sessions still open.
        output_path: Destination file path.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in sorted(error_counts.items()):
        lines.append(f"  <li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>", "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>"])

    for endpoint, times in sorted(api_latencies.items()):
        avg = sum(times) / len(times)
        lines.append(f"  <tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend(["</table>", "<h2>Active Sessions</h2>", f"<p>{active_session_count} user(s) currently active</p>", "</body>", "</html>"])

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


# ----------------------------------------------------------------------
# ORCHESTRATION
# ----------------------------------------------------------------------
def run_pipeline() -> None:
    """Run the full ETL pipeline: extract → transform → load → report."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    diagnostics, sessions, api_stats = extract(LOG_FILE)
    error_counts, api_latencies = transform(diagnostics, api_stats)

    conn = sqlite3.connect(DB_PATH)
    try:
        load(conn, error_counts, api_latencies)
    finally:
        conn.close()

    generate_report(error_counts, api_latencies, len(sessions), REPORT_FILE)

    print(f"Job finished at {datetime.datetime.now().isoformat()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        # Bootstrap a minimal log for local testing
        sample = (
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        with open(LOG_FILE, "w") as f:
            f.write(sample)
        print(f"[bootstrap] Created sample log: {LOG_FILE}")

    run_pipeline()
