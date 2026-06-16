"""
Pipeline — extract server log events, aggregate metrics, store in SQLite, generate HTML report.

Usage:
    python pipeline_refactored.py

Environment variables (all optional, sensible defaults:
    LOG_FILE_PATH    — path to the server log file  (default: server.log)
    DB_PATH          — path to the SQLite database   (default: metrics.db)
"""

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from os import environ
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def get_config() -> dict[str, str]:
    """Read runtime config from environment variables with sensible defaults."""
    return {
        "log_file": environ.get("LOG_FILE_PATH", "server.log"),
        "db_path": environ.get("DB_PATH", "metrics.db"),
    }


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LogEvent:
    """A single parsed event from a server log line."""

    timestamp: str
    level: str  # 'ERROR' | 'WARN' | 'INFO'
    message: str | None = None
    user_id: str | None = None
    action: str | None = None
    endpoint: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>INFO|ERROR|WARN|DEBUG)\s+"
    r"(?P<message>.+)$"
)

_USER_PATTERN = re.compile(r"^User\s+(?P<user_id>\S+)\s+(?P<action>.+)$")
_API_PATTERN = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


def _parse_log_event(line: str) -> LogEvent | None:
    """Parse a single log line into a *LogEvent*, or return *None* for unrecognised lines."""
    m = _LOG_LINE_PATTERN.match(line.strip())
    if not m:
        return None

    ts = m.group("timestamp")
    level = m.group("level")
    msg = m.group("message")

    if level == "ERROR":
        return LogEvent(timestamp=ts, level=level, message=msg)

    if level == "WARN":
        return LogEvent(timestamp=ts, level=level, message=msg)

    # INFO — dispatch on message content
    user_m = _USER_PATTERN.match(msg)
    if user_m:
        return LogEvent(
            timestamp=ts,
            level=level,
            user_id=user_m.group("user_id"),
            action=user_m.group("action"),
        )

    api_m = _API_PATTERN.match(msg)
    if api_m:
        dur_str = api_m.group("duration")
        return LogEvent(
            timestamp=ts,
            level=level,
            endpoint=api_m.group("endpoint"),
            duration_ms=int(dur_str) if dur_str else None,
        )

    return LogEvent(timestamp=ts, level=level, message=msg)


def extract_log_events(log_path: Path) -> list[LogEvent]:
    """Read a server log file and return every parsed *LogEvent*."""
    if not log_path.is_file():
        print(f"Log file not found: {log_path}")
        return []

    events: list[LogEvent] = []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            event = _parse_log_event(line)
            if event is not None:
                events.append(event)
    return events


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def aggregate_errors(events: list[LogEvent]) -> dict[str, int]:
    """Count occurrences of each unique error message."""
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        if e.level == "ERROR" and e.message is not None:
            counts[e.message] += 1
    return dict(counts)


def aggregate_api_latency(events: list[LogEvent]) -> dict[str, float]:
    """Compute average latency (ms) per API endpoint."""
    durations: dict[str, list[int]] = defaultdict(list)
    for e in events:
        if e.endpoint is not None and e.duration_ms is not None:
            durations[e.endpoint].append(e.duration_ms)

    return {ep: round(sum(times) / len(times), 1) for ep, times in durations.items()}


def count_active_sessions(events: list[LogEvent]) -> int:
    """Track log-in and log-out events, return the number of active sessions at end."""
    active: set[str] = set()
    for e in events:
        if e.user_id is None or e.action is None:
            continue
        if "logged in" in e.action:
            active.add(e.user_id)
        elif "logged out" in e.action:
            active.discard(e.user_id)
    return len(active)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_db(
    db_path: Path,
    error_summary: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Write aggregated metrics into SQLite using parameterised queries."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.now().isoformat()
        for msg, count in error_summary.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg_ms in api_latency.items():
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg_ms),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(
    error_summary: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: int,
) -> str:
    """Produce an HTML report string from the aggregated metrics."""
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_summary.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.extend(
        [
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    for ep, avg_ms in api_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{avg_ms}</td></tr>")
    lines.append("</table>")

    lines.extend(
        [
            "<h2>Active Sessions</h2>",
            f"<p>{active_sessions} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full ETL pipeline: extract → transform → load → report."""
    config = get_config()
    log_path = Path(config["log_file"])
    db_path = Path(config["db_path"])

    events = extract_log_events(log_path)

    error_summary = aggregate_errors(events)
    api_latency = aggregate_api_latency(events)
    active_sessions = count_active_sessions(events)

    print(f"Connecting to database: {db_path} ...")
    load_to_db(db_path, error_summary, api_latency)

    report_html = generate_report(error_summary, api_latency, active_sessions)
    report_path = Path("report.html")
    with report_path.open("w", encoding="utf-8") as f:
        f.write(report_html)

    print(f"Report written to {report_path}")
    print(f"Job finished at {datetime.now().isoformat()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _seed_demo_data(log_path: Path) -> None:
    """Create a sample log file if none exists (used only when run directly)."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with log_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)


def main() -> None:
    """Entry point — seed demo data if absent, then run the pipeline."""
    config = get_config()
    log_path = Path(config["log_file"])
    if not log_path.is_file():
        _seed_demo_data(log_path)
    run_pipeline()


if __name__ == "__main__":
    main()
