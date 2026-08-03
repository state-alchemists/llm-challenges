"""ETL pipeline: parse server logs, load metrics to SQLite, emit HTML report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_DB_PATH = "DB_PATH"
ENV_LOG_FILE = "LOG_FILE"
ENV_DB_HOST = "DB_HOST"
ENV_DB_PORT = "DB_PORT"
ENV_DB_USER = "DB_USER"
ENV_DB_PASS = "DB_PASS"

DEFAULT_DB_PATH = "metrics.db"
DEFAULT_LOG_FILE = "server.log"
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = "5432"
DEFAULT_DB_USER = "admin"
DEFAULT_DB_PASS = "password123"

DEMO_LOG_LINES: List[str] = [
    "2024-01-01 12:00:00 INFO User 42 logged in\n",
    "2024-01-01 12:05:00 ERROR Database timeout\n",
    "2024-01-01 12:05:05 ERROR Database timeout\n",
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
    "2024-01-01 12:10:00 INFO User 42 logged out\n",
]

# Regex for the outer log envelope: timestamp + level + payload
LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
)

# Regexes for structured INFO payloads
USER_RE = re.compile(r"^User (\S+) (.+)$")
API_RE = re.compile(r"^API (\S+) took (\d+)ms$")


@dataclass
class Config:
    """Runtime configuration read from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A user login/logout event extracted from a log entry."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call event extracted from a log entry."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedData:
    """Container for extracted log data."""
    errors: List[LogEntry] = field(default_factory=list)
    warnings: List[LogEntry] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)


@dataclass
class TransformedData:
    """Aggregated metrics ready for loading."""
    error_counts: Dict[str, int] = field(default_factory=dict)
    endpoint_latencies: Dict[str, float] = field(default_factory=dict)
    active_session_count: int = 0


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults.

    Returns:
        A populated Config instance.
    """
    return Config(
        db_path=os.getenv(ENV_DB_PATH, DEFAULT_DB_PATH),
        log_file=os.getenv(ENV_LOG_FILE, DEFAULT_LOG_FILE),
        db_host=os.getenv(ENV_DB_HOST, DEFAULT_DB_HOST),
        db_port=int(os.getenv(ENV_DB_PORT, DEFAULT_DB_PORT)),
        db_user=os.getenv(ENV_DB_USER, DEFAULT_DB_USER),
        db_pass=os.getenv(ENV_DB_PASS, DEFAULT_DB_PASS),
    )


def ensure_demo_log_file(path: str) -> None:
    """Create a demo log file if none exists so the pipeline can be exercised.

    Args:
        path: Filesystem path for the log file.
    """
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as fh:
        for line in DEMO_LOG_LINES:
            fh.write(line)


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a raw log line using regex.

    Args:
        line: Raw text from the log file.

    Returns:
        A LogEntry if the line matches the expected format, otherwise None.
    """
    match = LOG_RE.match(line.strip())
    if not match:
        return None
    timestamp, level, message = match.groups()
    return LogEntry(timestamp=timestamp, level=level, message=message)


def extract(log_path: str) -> ParsedData:
    """Read the server log and parse structured events.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ParsedData container holding all extracted events.
    """
    data = ParsedData()

    with open(log_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            entry = parse_log_line(raw_line)
            if entry is None:
                continue

            if entry.level == "ERROR":
                data.errors.append(entry)
            elif entry.level == "WARN":
                data.warnings.append(entry)
            elif entry.level == "INFO":
                user_match = USER_RE.match(entry.message)
                if user_match:
                    user_id, action = user_match.groups()
                    data.user_events.append(
                        UserEvent(
                            timestamp=entry.timestamp,
                            user_id=user_id,
                            action=action,
                        )
                    )
                    if "logged in" in action:
                        data.active_sessions[user_id] = entry.timestamp
                    elif "logged out" in action and user_id in data.active_sessions:
                        data.active_sessions.pop(user_id)
                    continue

                api_match = API_RE.match(entry.message)
                if api_match:
                    endpoint, duration_str = api_match.groups()
                    data.api_calls.append(
                        ApiCall(
                            timestamp=entry.timestamp,
                            endpoint=endpoint,
                            duration_ms=int(duration_str),
                        )
                    )

    return data


def transform(parsed: ParsedData) -> TransformedData:
    """Aggregate extracted events into metrics.

    Args:
        parsed: The output of the extract phase.

    Returns:
        A TransformedData container with computed summaries.
    """
    error_counts: Dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        endpoint_stats.setdefault(call.endpoint, []).append(call.duration_ms)

    endpoint_latencies: Dict[str, float] = {}
    for endpoint, times in endpoint_stats.items():
        endpoint_latencies[endpoint] = sum(times) / len(times)

    return TransformedData(
        error_counts=error_counts,
        endpoint_latencies=endpoint_latencies,
        active_session_count=len(parsed.active_sessions),
    )


def load(db_path: str, data: TransformedData) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        data: Aggregated metrics from the transform phase.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    cursor.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        [(now, msg, count) for msg, count in data.error_counts.items()],
    )

    cursor.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        [(now, ep, avg) for ep, avg in data.endpoint_latencies.items()],
    )

    conn.commit()
    conn.close()


def generate_html(data: TransformedData) -> str:
    """Build an HTML report from the transformed metrics.

    Args:
        data: Aggregated metrics.

    Returns:
        A complete HTML document string.
    """
    lines: List[str] = [
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

    for ep, avg in data.endpoint_latencies.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{data.active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def run_pipeline(config: Config) -> None:
    """Orchestrate Extract → Transform → Load and emit the report.

    Args:
        config: Pipeline configuration.
    """
    print(
        f"Connecting to {config.db_host}:{config.db_port} "
        f"as {config.db_user}..."
    )

    ensure_demo_log_file(config.log_file)

    parsed = extract(config.log_file)
    metrics = transform(parsed)
    load(config.db_path, metrics)

    html = generate_html(metrics)
    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    cfg = load_config()
    run_pipeline(cfg)
