"""Server log processing pipeline with ETL architecture.

Extracts structured data from plain-text server logs, aggregates metrics,
persists them to SQLite, and emits an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, NamedTuple, Tuple


class ParsedLine(NamedTuple):
    """A single parsed log line."""

    timestamp: str
    level: str
    raw_message: str


class ErrorRecord(NamedTuple):
    """Aggregated error data ready for the database and report."""

    message: str
    occurrence_count: int


class ApiLatencyRecord(NamedTuple):
    """Aggregated API latency data ready for the database and report."""

    endpoint: str
    avg_ms: float


def load_config() -> Dict[str, str]:
    """Read runtime configuration from environment variables.

    Returns:
        A mapping of setting names to string values.
    """
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def _create_demo_log_file(log_file: str) -> None:
    """Seed a demo log file if none exists so the script is runnable out-of-the-box."""
    if os.path.exists(log_file):
        return
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
)

_USER_RE = re.compile(r"^User (\d+) (.+)$")
_API_RE = re.compile(r"^API (\S+) took (\d+)ms$")


def extract_lines(log_file: str) -> List[ParsedLine]:
    """Parse every line in *log_file* into structured ``ParsedLine`` objects.

    Args:
        log_file: Path to the plain-text log file.

    Returns:
        A list of successfully parsed lines. Malformed lines are silently skipped.
    """
    lines: List[ParsedLine] = []
    with open(log_file, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            m = _LOG_RE.match(raw)
            if not m:
                continue
            timestamp, level, message = m.groups()
            lines.append(ParsedLine(timestamp=timestamp, level=level, raw_message=message))
    return lines


def extract_sessions(parsed_lines: List[ParsedLine]) -> Dict[str, str]:
    """Build a map of currently-active user sessions from parsed log lines.

    Args:
        parsed_lines: Lines already parsed by :func:`extract_lines`.

    Returns:
        Mapping of ``user_id -> login_timestamp`` for users who are still logged in.
    """
    sessions: Dict[str, str] = {}
    for line in parsed_lines:
        if line.level != "INFO":
            continue
        m = _USER_RE.match(line.raw_message)
        if not m:
            continue
        user_id, action = m.groups()
        if "logged in" in action:
            sessions[user_id] = line.timestamp
        elif "logged out" in action and user_id in sessions:
            sessions.pop(user_id)
    return sessions


def extract_api_calls(parsed_lines: List[ParsedLine]) -> List[Dict[str, str | int]]:
    """Pull API latency records out of the parsed log lines.

    Args:
        parsed_lines: Lines already parsed by :func:`extract_lines`.

    Returns:
        A list of dictionaries with keys ``d`` (timestamp), ``endpoint``, and ``ms``.
    """
    calls: List[Dict[str, str | int]] = []
    for line in parsed_lines:
        if line.level != "INFO":
            continue
        m = _API_RE.match(line.raw_message)
        if not m:
            continue
        endpoint, duration = m.groups()
        calls.append(
            {"d": line.timestamp, "endpoint": endpoint, "ms": int(duration)}
        )
    return calls


def extract_errors(parsed_lines: List[ParsedLine]) -> List[Dict[str, str]]:
    """Pull error and warning records out of the parsed log lines.

    Args:
        parsed_lines: Lines already parsed by :func:`extract_lines`.

    Returns:
        A list of dictionaries with keys ``d`` (timestamp), ``t`` (type), and ``m`` (message).
    """
    errors: List[Dict[str, str]] = []
    for line in parsed_lines:
        if line.level == "ERROR":
            errors.append({"d": line.timestamp, "t": "ERR", "m": line.raw_message})
        elif line.level == "WARN":
            errors.append({"d": line.timestamp, "t": "WARN", "m": line.raw_message})
    return errors


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_errors(error_records: List[Dict[str, str]]) -> List[ErrorRecord]:
    """Aggregate duplicate error messages and count occurrences.

    Args:
        error_records: Raw error dictionaries from :func:`extract_errors`.

    Returns:
        A list of ``ErrorRecord`` objects ready for persistence / reporting.
    """
    counts: Dict[str, int] = defaultdict(int)
    for rec in error_records:
        if rec["t"] == "ERR":
            counts[rec["m"]] += 1
    return [ErrorRecord(message=msg, occurrence_count=cnt) for msg, cnt in counts.items()]


def transform_api_latency(
    api_calls: List[Dict[str, str | int]],
) -> List[ApiLatencyRecord]:
    """Compute average latency per API endpoint.

    Args:
        api_calls: Raw API call dictionaries from :func:`extract_api_calls`.

    Returns:
        A list of ``ApiLatencyRecord`` objects ready for persistence / reporting.
    """
    buckets: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        buckets[str(call["endpoint"])].append(int(call["ms"]))
    return [
        ApiLatencyRecord(endpoint=ep, avg_ms=sum(times) / len(times))
        for ep, times in buckets.items()
    ]


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    errors: List[ErrorRecord],
    api_latencies: List[ApiLatencyRecord],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        errors: Aggregated error records.
        api_latencies: Aggregated API latency records.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

        for rec in errors:
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, rec.message, rec.occurrence_count),
            )

        for rec in api_latencies:
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, rec.endpoint, round(rec.avg_ms, 6)),
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    errors: List[ErrorRecord],
    api_latencies: List[ApiLatencyRecord],
    active_sessions: Dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Write an HTML report summarising errors, API latency, and active sessions.

    Args:
        errors: Aggregated error records.
        api_latencies: Aggregated API latency records.
        active_sessions: Mapping of active user IDs to login timestamps.
        output_path: Destination file path for the HTML report.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for rec in errors:
        escaped = rec.message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"<li><b>{escaped}</b>: {rec.occurrence_count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for rec in api_latencies:
        lines.append(
            f"<tr><td>{rec.endpoint}</td><td>{round(rec.avg_ms, 1)}</td></tr>"
        )

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Orchestrate the full Extract -> Transform -> Load workflow."""
    config = load_config()
    _create_demo_log_file(config["log_file"])

    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    # Extract
    parsed = extract_lines(config["log_file"])
    sessions = extract_sessions(parsed)
    api_calls = extract_api_calls(parsed)
    error_raw = extract_errors(parsed)

    # Transform
    errors = transform_errors(error_raw)
    api_latencies = transform_api_latency(api_calls)

    # Load
    load_to_database(config["db_path"], errors, api_latencies)
    generate_report(errors, api_latencies, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
