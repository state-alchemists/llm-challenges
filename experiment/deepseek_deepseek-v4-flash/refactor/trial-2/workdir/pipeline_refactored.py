"""Server log pipeline — extract, transform, and load.

Reads a server log file, parses structured events, aggregates error and API
metrics into SQLite, and produces an HTML report.
"""

import datetime
import os
import re
import sqlite3
from collections.abc import Iterator
from typing import NamedTuple


# ── Configuration ──────────────────────────────────────────────────────

def _env_str(name: str, default: str) -> str:
    """Read a string config value from the environment."""
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    """Read an integer config value from the environment."""
    return int(os.environ.get(name, str(default)))


DB_PATH = _env_str("PIPELINE_DB_PATH", "metrics.db")
LOG_FILE = _env_str("PIPELINE_LOG_FILE", "server.log")
# The following are read from env for forward compatibility if a real RDBMS
# replaces SQLite; currently only used for the connection print statement.
DB_HOST = _env_str("PIPELINE_DB_HOST", "localhost")
DB_PORT = _env_int("PIPELINE_DB_PORT", 5432)
DB_USER = _env_str("PIPELINE_DB_USER", "admin")
DB_PASS = _env_str("PIPELINE_DB_PASS", "password123")

# ── Regex patterns ─────────────────────────────────────────────────────

_LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|WARN|INFO) "
    r"(?P<message>.+)"
)

_USER_PATTERN = re.compile(r"^User (\d+) (.+)$")

_API_PATTERN = re.compile(r"^API (\S+) took (\d+)ms$")


# ── Data containers ────────────────────────────────────────────────────

class ApiCall(NamedTuple):
    """A single API call recorded in the log."""

    timestamp: str
    endpoint: str
    duration_ms: int


# ── Phase 1: Extract ───────────────────────────────────────────────────

def read_log_lines(path: str) -> Iterator[str]:
    """Yield non-empty lines from *path*, or do nothing if missing."""
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                yield stripped


def parse_log_line(line: str) -> dict | None:
    """Parse a log *line* into a dict with keys *timestamp*, *level*, *message*.

    Returns ``None`` when the line does not match the expected format.
    """
    m = _LOG_PATTERN.match(line)
    if m is None:
        return None
    return m.groupdict()


def extract(path: str) -> tuple[dict[str, int], list[ApiCall], dict[str, str]]:
    """Read and parse *path*, returning (error_counts, api_calls, sessions).

    *error_counts* maps error message text → occurrence count.
    *api_calls* is a list of API call records with duration.
    *sessions* maps user id → login timestamp for currently-active users.
    """
    error_counts: dict[str, int] = {}
    api_calls: list[ApiCall] = []
    sessions: dict[str, str] = {}

    for line in read_log_lines(path):
        entry = parse_log_line(line)
        if entry is None:
            continue

        level = entry["level"]
        ts = entry["timestamp"]
        msg = entry["message"]

        if level == "ERROR":
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif level == "WARN":
            pass  # warnings are logged but not included in the report

        elif level == "INFO":
            _process_info_line(ts, msg, api_calls, sessions)

    return error_counts, api_calls, sessions


def _process_info_line(
    ts: str,
    msg: str,
    api_calls: list[ApiCall],
    sessions: dict[str, str],
) -> None:
    """Dispatch an INFO-level message to the appropriate collector."""
    user_m = _USER_PATTERN.match(msg)
    if user_m:
        uid, action = user_m.group(1), user_m.group(2)
        if "logged in" in action:
            sessions[uid] = ts
        elif "logged out" in action and uid in sessions:
            sessions.pop(uid, None)
        return

    api_m = _API_PATTERN.match(msg)
    if api_m:
        endpoint, duration_str = api_m.group(1), api_m.group(2)
        api_calls.append(ApiCall(timestamp=ts, endpoint=endpoint, duration_ms=int(duration_str)))


# ── Phase 2: Transform ─────────────────────────────────────────────────

def compute_api_stats(api_calls: list[ApiCall]) -> dict[str, float]:
    """Return *endpoint* → average duration in ms."""
    totals: dict[str, list[int]] = {}
    for call in api_calls:
        totals.setdefault(call.endpoint, []).append(call.duration_ms)
    return {ep: sum(times) / len(times) for ep, times in totals.items()}


# ── Phase 3: Load ──────────────────────────────────────────────────────

def _announce_connection() -> None:
    """Print a connection banner (informational only)."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")


def init_database(db_path: str) -> sqlite3.Connection:
    """Create/connect to SQLite at *db_path* and ensure tables exist."""
    _announce_connection()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def store_errors(
    conn: sqlite3.Connection, timestamp: str, error_counts: dict[str, int]
) -> None:
    """Insert aggregated error records using parameterized queries."""
    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (timestamp, msg, count),
        )


def store_api_metrics(
    conn: sqlite3.Connection, timestamp: str, api_stats: dict[str, float]
) -> None:
    """Insert API latency records using parameterized queries."""
    for endpoint, avg_ms in api_stats.items():
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (timestamp, endpoint, avg_ms),
        )


def generate_html_report(
    error_counts: dict[str, int],
    api_stats: dict[str, float],
    active_session_count: int,
) -> str:
    """Build the ``report.html`` string from aggregated metrics."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in sorted(api_stats.items()):
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(lines)


def write_report(path: str, html: str) -> None:
    """Persist *html* to *path*."""
    with open(path, "w") as f:
        f.write(html)


# ── Pipeline entry point ───────────────────────────────────────────────

def run_pipeline() -> None:
    """Execute the full extract → transform → load pipeline."""
    error_counts, api_calls, sessions = extract(LOG_FILE)
    api_stats = compute_api_stats(api_calls)
    active_session_count = len(sessions)

    now = datetime.datetime.now().isoformat()
    conn = init_database(DB_PATH)
    try:
        store_errors(conn, now, error_counts)
        store_api_metrics(conn, now, api_stats)
        conn.commit()
    finally:
        conn.close()

    html = generate_html_report(error_counts, api_stats, active_session_count)
    write_report("report.html", html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
