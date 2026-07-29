"""
Pipeline: Extract, Transform, Load server logs into a report.

Reads server log files, parses each line with regex, aggregates error
summaries and API latency metrics, stores results in SQLite (parameterized
queries), and generates an HTML report.

All configuration is read from environment variables.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from html import escape as html_escape
from pathlib import Path


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class Config:
    """Application configuration sourced from environment variables."""

    db_path: str = "metrics.db"
    log_file: str = "server.log"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "admin"
    db_pass: str = "password123"


def load_config() -> Config:
    """Read configuration from environment variables with sensible defaults."""
    return Config(
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        log_file=os.environ.get("LOG_FILE", "server.log"),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_user=os.environ.get("DB_USER", "admin"),
        db_pass=os.environ.get("DB_PASS", "password123"),
    )


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class LogEntry:
    """A single parsed log line with typed fields per log level."""

    timestamp: str
    level: str
    message: str
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ── Extract: log parsing ─────────────────────────────────────────────────────


_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
)

_USER_PATTERN = re.compile(r"^User (\d+) (logged in|logged out)$")

_API_PATTERN = re.compile(r"^API (\S+) took (\d+)ms$")


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a structured LogEntry.

    Returns None for malformed lines that don't match the expected format.
    """
    m = _LOG_PATTERN.match(line.strip())
    if not m:
        return None
    ts, level, rest = m.groups()

    if level == "ERROR":
        return LogEntry(timestamp=ts, level="ERROR", message=rest)

    if level == "WARN":
        return LogEntry(timestamp=ts, level="WARN", message=rest)

    # --- level is INFO ---
    um = _USER_PATTERN.match(rest)
    if um:
        uid, action = um.groups()
        return LogEntry(
            timestamp=ts,
            level="USR",
            message=rest,
            user_id=uid,
            action=action,
        )

    am = _API_PATTERN.match(rest)
    if am:
        endpoint, dur = am.groups()
        return LogEntry(
            timestamp=ts,
            level="API",
            message=rest,
            endpoint=endpoint,
            duration_ms=int(dur),
        )

    return LogEntry(timestamp=ts, level="INFO", message=rest)


def extract_logs(filepath: str) -> list[LogEntry]:
    """Read and parse every line in the log file.

    Silently skips blank or malformed lines.
    """
    path = Path(filepath)
    if not path.exists():
        return []

    entries: list[LogEntry] = []
    with path.open("r") as f:
        for raw_line in f:
            entry = parse_log_line(raw_line)
            if entry is not None:
                entries.append(entry)
    return entries


# ── Transform: aggregation ───────────────────────────────────────────────────


def track_sessions(entries: list[LogEntry]) -> dict[str, str]:
    """Replay login/logout events to determine active sessions.

    Returns a dict of {user_id: login_timestamp} for sessions still
    active at the end of the log.
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if e.level != "USR" or e.user_id is None or e.action is None:
            continue
        if "logged in" in e.action:
            sessions[e.user_id] = e.timestamp
        elif "logged out" in e.action and e.user_id in sessions:
            del sessions[e.user_id]
    return sessions


def summarize_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each unique error message."""
    counts: dict[str, int] = {}
    for e in entries:
        if e.level == "ERROR":
            counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def compute_api_latency(entries: list[LogEntry]) -> dict[str, float]:
    """Compute average latency (ms) per API endpoint."""
    times: dict[str, list[int]] = {}
    for e in entries:
        if e.level == "API" and e.endpoint is not None and e.duration_ms is not None:
            times.setdefault(e.endpoint, []).append(e.duration_ms)

    return {ep: sum(vals) / len(vals) for ep, vals in times.items()}


# ── Load: database ───────────────────────────────────────────────────────────


def init_db(db_path: str) -> sqlite3.Connection:
    """Open the SQLite database and ensure required tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def load_errors_to_db(
    conn: sqlite3.Connection, counts: dict[str, int]
) -> None:
    """Insert error summary rows using parameterized queries."""
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, cnt) for msg, cnt in counts.items()],
    )
    conn.commit()


def load_api_metrics_to_db(
    conn: sqlite3.Connection, averages: dict[str, float]
) -> None:
    """Insert API latency rows using parameterized queries."""
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in averages.items()],
    )
    conn.commit()


# ── Load: HTML report ────────────────────────────────────────────────────────


def generate_html_report(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    active_session_count: int,
) -> str:
    """Build the full HTML report string with error, latency, and session data."""
    parts: list[str] = [
        "<html>\n<head><title>System Report</title></head>\n<body>\n",
        "<h1>Error Summary</h1>\n<ul>\n",
    ]

    for err_msg, count in error_counts.items():
        parts.append(
            f"<li><b>{html_escape(err_msg)}</b>: {count} occurrences</li>\n"
        )
    parts.append("</ul>\n")

    parts.append(
        "<h2>API Latency</h2>\n<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    )
    for ep, avg in sorted(api_latency.items()):
        parts.append(f"<tr><td>{html_escape(ep)}</td><td>{avg:.1f}</td></tr>\n")
    parts.append("</table>\n")

    parts.append("<h2>Active Sessions</h2>\n")
    parts.append(f"<p>{active_session_count} user(s) currently active</p>\n")
    parts.append("</body>\n</html>")

    return "".join(parts)


def write_report(html: str, output_path: str = "report.html") -> None:
    """Write the HTML report to disk."""
    Path(output_path).write_text(html)


# ── Pipeline orchestrator ────────────────────────────────────────────────────


def run_pipeline() -> None:
    """Orchestrate Extract → Transform → Load for the log report."""
    config = load_config()

    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )

    entries = extract_logs(config.log_file)

    sessions = track_sessions(entries)
    error_counts = summarize_errors(entries)
    api_latency = compute_api_latency(entries)

    conn = init_db(config.db_path)
    try:
        load_errors_to_db(conn, error_counts)
        load_api_metrics_to_db(conn, api_latency)
    finally:
        conn.close()

    html = generate_html_report(error_counts, api_latency, len(sessions))
    write_report(html)

    print(f"Job finished at {datetime.datetime.now()}")


# ── Entry point ──────────────────────────────────────────────────────────────


if __name__ == "__main__":
    log_file = os.environ.get("LOG_FILE", "server.log")
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
