"""Refactored pipeline: extract server logs, transform metrics, load to SQLite, generate HTML report."""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration loaded from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_path: str


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults."""
    return Config(
        db_path=os.getenv("METRICS_DB_PATH", "metrics.db"),
        log_file=os.getenv("SERVER_LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
        report_path=os.getenv("REPORT_PATH", "report.html"),
    )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LogEvent:
    """A single parsed log line."""
    dt: str
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEvent:
    """A parsed user login/logout event."""
    dt: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiCall:
    """A parsed API call event."""
    dt: str
    endpoint: str
    ms: int


# ---------------------------------------------------------------------------
# Regex patterns (compiled once)
# ---------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<level>\w+)\s+(?P<rest>.*)$"
)
_USER_RE = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.+)$")
_API_RE = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?$")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------
def extract_events(log_path: str) -> tuple[list[LogEvent], list[UserEvent], list[ApiCall]]:
    """Parse a server log file into structured events.

    Args:
        log_path: Path to the log file.

    Returns:
        A 3-tuple of (generic log events, user events, API call events).
    """
    log_events: list[LogEvent] = []
    user_events: list[UserEvent] = []
    api_calls: list[ApiCall] = []

    path = Path(log_path)
    if not path.exists():
        return log_events, user_events, api_calls

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            dt = match.group("dt")
            level = match.group("level")
            rest = match.group("rest")

            if level == "INFO":
                user_match = _USER_RE.match(rest)
                if user_match:
                    user_events.append(
                        UserEvent(
                            dt=dt,
                            user_id=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                    continue

                api_match = _API_RE.match(rest)
                if api_match:
                    dur_str = api_match.group("dur")
                    api_calls.append(
                        ApiCall(
                            dt=dt,
                            endpoint=api_match.group("endpoint"),
                            ms=int(dur_str) if dur_str is not None else 0,
                        )
                    )
                    continue

            # Treat ERROR, WARN, and unmatched INFO lines as generic log events.
            log_events.append(LogEvent(dt=dt, level=level, message=rest))

    return log_events, user_events, api_calls


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TransformedData:
    """Aggregated metrics ready for loading and reporting."""
    error_counts: dict[str, int] = field(default_factory=dict)
    api_latency: dict[str, float] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


def transform(
    log_events: list[LogEvent],
    user_events: list[UserEvent],
    api_calls: list[ApiCall],
) -> TransformedData:
    """Aggregate raw events into metrics.

    Args:
        log_events: Generic log events (ERROR, WARN, etc.).
        user_events: Parsed user login/logout events.
        api_calls: Parsed API call events.

    Returns:
        TransformedData containing error counts, API latency averages,
        and the current active session map.
    """
    # Count ERROR-level events by message.
    error_counts: dict[str, int] = {}
    for ev in log_events:
        if ev.level == "ERROR":
            error_counts[ev.message] = error_counts.get(ev.message, 0) + 1

    # Track active sessions from user events.
    active_sessions: dict[str, str] = {}
    for ev in user_events:
        if "logged in" in ev.action:
            active_sessions[ev.user_id] = ev.dt
        elif "logged out" in ev.action and ev.user_id in active_sessions:
            active_sessions.pop(ev.user_id)

    # Compute average latency per endpoint.
    endpoint_times: dict[str, list[int]] = {}
    for call in api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.ms)

    api_latency: dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_times.items()
    }

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=active_sessions,
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_to_database(config: Config, data: TransformedData) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        config: Runtime configuration containing the DB path.
        data: Aggregated metrics to persist.
    """
    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        for msg, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg in data.api_latency.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(config: Config, data: TransformedData) -> None:
    """Write an HTML report summarizing the transformed metrics.

    Args:
        config: Runtime configuration containing the report output path.
        data: Aggregated metrics to render.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in data.api_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(data.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    Path(config.report_path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the full ETL pipeline."""
    config = load_config()
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    log_events, user_events, api_calls = extract_events(config.log_file)
    data = transform(log_events, user_events, api_calls)
    load_to_database(config, data)
    generate_report(config, data)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
