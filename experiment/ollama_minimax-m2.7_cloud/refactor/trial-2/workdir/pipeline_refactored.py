"""
Pipeline: Parse server logs, persist metrics to SQLite, generate HTML report.

Architecture follows the ETL pattern:
    Extract  → parse_log_file()      reads and tokenizes log entries
    Transform → build_metrics()       aggregates errors, latency, sessions
    Load     → persist_metrics()      writes to SQLite using parameterized queries
    Report   → generate_html_report() produces report.html

All configuration is driven by environment variables (see DEFAULT_CONFIG).
"""

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ErrorEntry(TypedDict):
    timestamp: str
    type: str
    message: str


class UserActionEntry(TypedDict):
    timestamp: str
    type: str
    user_id: str
    action: str


class ApiCallEntry(TypedDict):
    timestamp: str
    type: str
    endpoint: str
    latency_ms: int


class WarnEntry(TypedDict):
    timestamp: str
    type: str
    message: str


ParsedLog = list[ErrorEntry | UserActionEntry | ApiCallEntry | WarnEntry]


class AggregatedMetrics(TypedDict):
    error_counts: dict[str, int]
    endpoint_latencies: dict[str, list[int]]
    active_sessions: dict[str, str]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Config:
    """Holds pipeline configuration sourced from environment variables."""

    DB_PATH: Path
    LOG_FILE: Path
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str

    def __init__(self) -> None:
        self.DB_PATH = Path(os.environ.get("PIPELINE_DB_PATH", "metrics.db"))
        self.LOG_FILE = Path(os.environ.get("PIPELINE_LOG_FILE", "server.log"))
        self.DB_HOST = os.environ.get("PIPELINE_DB_HOST", "localhost")
        self.DB_PORT = int(os.environ.get("PIPELINE_DB_PORT", "5432"))
        self.DB_USER = os.environ.get("PIPELINE_DB_USER", "admin")
        self.DB_PASS = os.environ.get("PIPELINE_DB_PASS", "")

    def __repr__(self) -> str:
        # Omit password from repr
        return (
            f"Config(DB_PATH={self.DB_PATH}, LOG_FILE={self.LOG_FILE}, "
            f"DB_HOST={self.DB_HOST}, DB_PORT={self.DB_PORT}, "
            f"DB_USER={self.DB_USER}, DB_PASS=***)"
        )


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


# Compiled once at import time — match objects are reusable across lines.
_RE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN)\s+"
    r"(?P<body>.*)"
)
_RE_USER_ACTION = re.compile(r"User\s+(?P<user_id>\S+)\s+(?P<action>.+)")
_RE_API_CALL = re.compile(r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<latency>\d+)ms")


def parse_log_file(path: Path) -> tuple[ParsedLog, dict[str, str]]:
    """
    Parse a server log file and return structured entries plus active sessions.

    Each line is classified as ERROR, INFO (user action), INFO (API call), or WARN.

    Returns:
        A (entries, sessions) pair where:
        - entries: one TypedDict per log line (type field discriminates the variant)
        - sessions: {user_id: last_seen_timestamp} for users who logged in
                     but have not yet logged out
    """
    entries: ParsedLog = []
    sessions: dict[str, str] = {}

    if not path.exists():
        return entries, sessions

    with path.open() as f:
        for line in f:
            line = line.rstrip("\n")
            m = _RE_LOG_LINE.match(line)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            body = m.group("body")

            if level == "ERROR":
                entries.append(ErrorEntry(timestamp=timestamp, type="ERR", message=body))

            elif level == "WARN":
                entries.append(WarnEntry(timestamp=timestamp, type="WARN", message=body))

            elif level == "INFO":
                # Try user action first
                user_m = _RE_USER_ACTION.match(body)
                if user_m:
                    user_id = user_m.group("user_id")
                    action = user_m.group("action")
                    entries.append(
                        UserActionEntry(
                            timestamp=timestamp, type="USR", user_id=user_id, action=action
                        )
                    )
                    if "logged in" in action:
                        sessions[user_id] = timestamp
                    elif "logged out" in action and user_id in sessions:
                        sessions.pop(user_id)
                    continue

                # Try API call
                api_m = _RE_API_CALL.match(body)
                if api_m:
                    entries.append(
                        ApiCallEntry(
                            timestamp=timestamp,
                            type="API",
                            endpoint=api_m.group("endpoint"),
                            latency_ms=int(api_m.group("latency")),
                        )
                    )

    return entries, sessions


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def build_metrics(entries: ParsedLog) -> AggregatedMetrics:
    """
    Aggregate parsed log entries into error counts, endpoint latencies, and sessions.

    Returns:
        AggregatedMetrics containing:
        - error_counts: {error_message: count}
        - endpoint_latencies: {endpoint: [latency_ms, ...]}
        - active_sessions: {user_id: login_timestamp}  (populated from sessions arg)
    """
    error_counts: dict[str, int] = {}
    endpoint_latencies: dict[str, list[int]] = {}

    for entry in entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif entry["type"] == "API":
            ep = entry["endpoint"]
            endpoint_latencies.setdefault(ep, []).append(entry["latency_ms"])

    return AggregatedMetrics(
        error_counts=error_counts,
        endpoint_latencies=endpoint_latencies,
        active_sessions={},
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def persist_metrics(db_path: Path, metrics: AggregatedMetrics) -> None:
    """
    Write aggregated metrics into SQLite using parameterized queries.

    Two tables are created if absent:
        errors     (dt TEXT, message TEXT, count INTEGER)
        api_metrics(dt TEXT, endpoint TEXT, avg_ms REAL)

    Args:
        db_path:  path to the SQLite database file
        metrics:  aggregated error counts and endpoint latencies
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

    # Parameterized INSERT — safe against injection
    for msg, count in metrics["error_counts"].items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, latencies in metrics["endpoint_latencies"].items():
        avg_ms = sum(latencies) / len(latencies)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_html_report(
    output_path: Path,
    metrics: AggregatedMetrics,
    active_sessions: dict[str, str],
) -> None:
    """
    Write report.html with error summary, API latency table, and active session count.

    Args:
        output_path:       destination file path
        metrics:           aggregated error counts and latencies
        active_sessions:   {user_id: login_timestamp} for still-active sessions
    """
    error_counts = metrics["error_counts"]
    endpoint_latencies = metrics["endpoint_latencies"]
    session_count = len(active_sessions)

    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")
    lines.append("<h1>Error Summary</h1>")

    if error_counts:
        lines.append("<ul>")
        for msg, count in error_counts.items():
            lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
        lines.append("</ul>")
    else:
        lines.append("<p>No errors recorded.</p>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for ep, latencies in endpoint_latencies.items():
        avg = sum(latencies) / len(latencies)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline(config: Config) -> None:
    """
    Execute the full ETL pipeline: extract → transform → load → report.

    Args:
        config: populated Config instance
    """
    print(
        f"Connecting to {config.DB_HOST}:{config.DB_PORT} as {config.DB_USER}..."
    )

    # Extract
    entries, active_sessions = parse_log_file(config.LOG_FILE)

    # Transform
    metrics = build_metrics(entries)

    # Load
    persist_metrics(config.DB_PATH, metrics)

    # Report
    generate_html_report(Path("report.html"), metrics, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    # Bootstrap a minimal test log when the file is missing (same behaviour as original)
    LOG_PATH = Path(os.environ.get("PIPELINE_LOG_FILE", "server.log"))
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
        print(f"Created sample {LOG_PATH} — run again to process it.")

    config = Config()
    run_pipeline(config)
