"""Server log processing pipeline.

Reads server logs, extracts structured events, persists aggregates to
SQLite, and emits an HTML report.

Refactored goals:
- Configuration lives entirely in environment variables.
- SQL injection eliminated via parameterized queries.
- Logic decomposed into Extract / Transform / Load phases.
- Regex-based log parsing replaces brittle string splitting.
- Full type hints and docstrings throughout.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_config() -> Dict[str, str]:
    """Read runtime configuration from environment variables.

    Supported variables:
    - ``DB_PATH``       : SQLite database file path.
    - ``LOG_FILE``      : Path to the server log file.
    - ``REPORT_PATH``   : Path for the generated HTML report.
    - ``DB_HOST``       : Database host (informational).
    - ``DB_PORT``       : Database port (informational).
    - ``DB_USER``       : Database username (informational).
    - ``DB_PASS``       : Database password (informational).

    Returns
    -------
    dict
        Mapping of variable name to resolved string value.
    """
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_path": os.getenv("LOG_FILE", "server.log"),
        "report_path": os.getenv("REPORT_PATH", "report.html"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ErrorRecord:
    """A single error or warning event extracted from a log line."""
    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user-centric log event (login or logout)."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API request log event."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedLog:
    """Container for all extracted events from the log file."""
    errors: List[ErrorRecord] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    warnings: List[ErrorRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_ERROR_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<msg>.*)$"
)

_USER_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<uid>\S+) (?P<action>.*)$"
)

_API_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+) took (?P<dur>\d+)ms$"
)

_WARN_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<msg>.*)$"
)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_logs(log_path: str) -> ParsedLog:
    """Parse *log_path* into structured events.

    Each line is matched against a set of regex patterns.  Unrecognised
    lines are silently skipped.

    Parameters
    ----------
    log_path:
        Filesystem path to the server log.

    Returns
    -------
    ParsedLog
        Aggregated errors, warnings, user events, and API calls.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        return parsed

    with open(log_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue

            m = _ERROR_RE.match(line)
            if m:
                parsed.errors.append(ErrorRecord(
                    timestamp=m.group("dt"),
                    message=m.group("msg"),
                ))
                continue

            m = _API_RE.match(line)
            if m:
                parsed.api_calls.append(ApiCall(
                    timestamp=m.group("dt"),
                    endpoint=m.group("endpoint"),
                    duration_ms=int(m.group("dur")),
                ))
                continue

            m = _USER_RE.match(line)
            if m:
                parsed.user_events.append(UserEvent(
                    timestamp=m.group("dt"),
                    user_id=m.group("uid"),
                    action=m.group("action"),
                ))
                continue

            m = _WARN_RE.match(line)
            if m:
                parsed.warnings.append(ErrorRecord(
                    timestamp=m.group("dt"),
                    message=m.group("msg"),
                ))

    return parsed


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

TransformResult = Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]


def transform_logs(parsed: ParsedLog) -> TransformResult:
    """Aggregate extracted events into summary statistics.

    Parameters
    ----------
    parsed:
        The output of :func:`extract_logs`.

    Returns
    -------
    Tuple[errors, api_stats, sessions]
        *errors* maps message text to occurrence count.
        *api_stats* maps endpoint paths to lists of duration samples.
        *sessions* maps active user IDs to their last login timestamp.
    """
    # Count errors (legacy behaviour ignores warnings for the report)
    errors: Dict[str, int] = {}
    for rec in parsed.errors:
        errors[rec.message] = errors.get(rec.message, 0) + 1

    # Bucket API latencies by endpoint
    api_stats: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        api_stats.setdefault(call.endpoint, []).append(call.duration_ms)

    # Track active sessions based on login / logout pairs
    sessions: Dict[str, str] = {}
    for evt in parsed.user_events:
        if "logged in" in evt.action:
            sessions[evt.user_id] = evt.timestamp
        elif "logged out" in evt.action and evt.user_id in sessions:
            sessions.pop(evt.user_id)

    return errors, api_stats, sessions


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    errors: Dict[str, int],
    api_stats: Dict[str, List[int]],
) -> None:
    """Persist aggregates to SQLite using parameterized queries.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    errors:
        Message → count mapping to insert into the ``errors`` table.
    api_stats:
        Endpoint → durations mapping to insert into the ``api_metrics``
        table.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors ("
            "dt TEXT, message TEXT, count INTEGER"
            ")"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics ("
            "dt TEXT, endpoint TEXT, avg_ms REAL"
            ")"
        )

        now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

        for msg, count in errors.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for endpoint, times in api_stats.items():
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, endpoint, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    errors: Dict[str, int],
    api_stats: Dict[str, List[int]],
    sessions: Dict[str, str],
    report_path: str,
) -> None:
    """Write the HTML report to *report_path*.

    The emitted document preserves the legacy sections:
    * Error Summary
    * API Latency table
    * Active Sessions count
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in errors.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.extend([
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, times in api_stats.items():
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.extend([
        "<h2>Active Sessions</h2>",
        f"<p>{len(sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline(config: Dict[str, str]) -> None:
    """Execute the full Extract → Transform → Load workflow.

    Parameters
    ----------
    config:
        Dictionary produced by :func:`_load_config`.
    """
    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    # Extract
    parsed = extract_logs(config["log_path"])

    # Transform
    errors, api_stats, sessions = transform_logs(parsed)

    # Load
    load_to_database(config["db_path"], errors, api_stats)

    # Report
    generate_report(
        errors,
        api_stats,
        sessions,
        config["report_path"],
    )

    print(f"Job finished at {datetime.datetime.now()}")


def main() -> None:
    """Bootstrap a missing demo log file and drive the pipeline."""
    cfg = _load_config()

    if not os.path.exists(cfg["log_path"]):
        with open(cfg["log_path"], "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline(cfg)


if __name__ == "__main__":
    main()
