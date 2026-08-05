"""Log processing pipeline: Extract → Transform → Load.

Produces an HTML report from server logs with error summaries,
API latency metrics, and active session counts.
"""

from __future__ import annotations

import os
import re
import sqlite3
import datetime
from typing import TypedDict


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------


class ErrorEntry(TypedDict):
    """A parsed ERROR log line."""
    dt: str
    t: str
    m: str


class UserEntry(TypedDict):
    """A parsed INFO User log line."""
    dt: str
    t: str
    u: str
    a: str


class ApiEntry(TypedDict):
    """A parsed INFO API log line."""
    dt: str
    t: str
    endpoint: str
    ms: int


class WarnEntry(TypedDict):
    """A parsed WARN log line."""
    dt: str
    t: str
    m: str


class ParsedLogs(TypedDict):
    """All log entries collected during extraction."""
    errors: list[ErrorEntry]
    users: list[UserEntry]
    api_calls: list[ApiEntry]
    warns: list[WarnEntry]


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------


def get_config() -> dict:
    """Load pipeline configuration from environment variables.

    Returns:
        Dictionary with keys: db_path, log_file, db_host, db_port,
        db_user, db_pass. Sensible defaults are provided for all values.

    Env vars:
        DB_PATH     Path to the SQLite database file.
        LOG_FILE    Path to the server log file.
        DB_HOST     Database host (used in informational print only).
        DB_PORT     Database port (used in informational print only).
        DB_USER     Database username (used in informational print only).
        DB_PASS     Database password (used in informational print only).
    """
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": int(os.environ.get("DB_PORT", "5432")),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", ""),
    }


# -----------------------------------------------------------------------------
# Extract
# -----------------------------------------------------------------------------


def parse_log_line(line: str) -> ErrorEntry | UserEntry | ApiEntry | WarnEntry | None:
    """Parse a single log line into a typed entry.

    Args:
        line: A raw line from the server log.

    Returns:
        A typed dict for the recognized log type, or None if unparseable.
    """
    # Generic header: timestamp + level + rest
    header_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+) (.+)$", line)
    if not header_match:
        return None

    dt, lvl, msg = header_match.group(1), header_match.group(2), header_match.group(3)

    if lvl == "ERROR":
        return ErrorEntry(dt=dt, t="ERR", m=msg)

    if lvl == "INFO":
        # User action line: "User <id> <action>"
        user_match = re.match(r"^User (\S+) (.+)$", msg)
        if user_match:
            uid, action = user_match.group(1), user_match.group(2)
            return UserEntry(dt=dt, t="USR", u=uid, a=action)

        # API latency line: "API <endpoint> took <n>ms"
        api_match = re.match(r"^API (\S+) took (\d+)ms$", msg)
        if api_match:
            endpoint, ms = api_match.group(1), int(api_match.group(2))
            return ApiEntry(dt=dt, t="API", endpoint=endpoint, ms=ms)

    if lvl == "WARN":
        return WarnEntry(dt=dt, t="WARN", m=msg)

    return None


def extract(log_file: str) -> ParsedLogs:
    """Read and parse all log entries from a file.

    Args:
        log_file: Path to the server log file.

    Returns:
        A ParsedLogs dict containing categorized entries.
    """
    errors: list[ErrorEntry] = []
    users: list[UserEntry] = []
    api_calls: list[ApiEntry] = []
    warns: list[WarnEntry] = []

    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return ParsedLogs(errors=errors, users=users, api_calls=api_calls, warns=warns)

    with open(log_file, "r") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is None:
                continue

            match entry["t"]:
                case "ERR":
                    errors.append(entry)  # type: ignore[arg-type]
                case "USR":
                    users.append(entry)  # type: ignore[arg-type]
                case "API":
                    api_calls.append(entry)  # type: ignore[arg-type]
                case "WARN":
                    warns.append(entry)  # type: ignore[arg-type]

    return ParsedLogs(errors=errors, users=users, api_calls=api_calls, warns=warns)


# -----------------------------------------------------------------------------
# Transform
# -----------------------------------------------------------------------------


def transform_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Aggregate error messages by text.

    Args:
        errors: List of parsed ERROR entries.

    Returns:
        Mapping from error message text to occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err["m"]] = counts.get(err["m"], 0) + 1
    return counts


def transform_api_latency(api_calls: list[ApiEntry]) -> dict[str, float]:
    """Compute average latency per endpoint.

    Args:
        api_calls: List of parsed API entries.

    Returns:
        Mapping from endpoint path to average response time in ms.
    """
    buckets: dict[str, list[int]] = {}
    for call in api_calls:
        buckets.setdefault(call["endpoint"], []).append(call["ms"])

    return {ep: sum(times) / len(times) for ep, times in buckets.items()}


def transform_active_sessions(users: list[UserEntry]) -> int:
    """Count currently-active sessions based on login/logout events.

    A user is considered active from their most recent login until their
    first subsequent logout. If a user logs in multiple times without
    logging out, only the last login is counted.

    Args:
        users: List of parsed user action entries, in chronological order.

    Returns:
        Number of currently active (logged-in, not-yet-logged-out) sessions.
    """
    active: dict[str, str] = {}  # uid -> login timestamp

    for event in users:
        uid, action = event["u"], event["a"]
        if "logged in" in action:
            active[uid] = event["dt"]
        elif "logged out" in action and uid in active:
            del active[uid]

    return len(active)


# -----------------------------------------------------------------------------
# Load
# -----------------------------------------------------------------------------


def load_to_db(
    db_path: str,
    errors: dict[str, int],
    api_latency: dict[str, float],
) -> None:
    """Write aggregated metrics into the SQLite database.

    Creates the tables if they do not exist. Uses parameterized queries
    to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        errors: Error message counts from transform_errors.
        api_latency: Endpoint average latencies from transform_api_latency.
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
    for msg, count in errors.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def load_to_html(
    output_path: str,
    errors: dict[str, int],
    api_latency: dict[str, float],
    active_sessions: int,
) -> None:
    """Write the HTML report to disk.

    Args:
        output_path: Destination file path for the HTML report.
        errors: Error message counts from transform_errors.
        api_latency: Endpoint average latencies from transform_api_latency.
        active_sessions: Session count from transform_active_sessions.
    """
    now = datetime.datetime.now().isoformat()

    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        f"<p>Generated: {now}</p>",
        "",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if errors:
        for msg, count in errors.items():
            lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    else:
        lines.append("<li>No errors recorded</li>")

    lines.extend([
        "</ul>",
        "",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    if api_latency:
        for endpoint, avg_ms in api_latency.items():
            lines.append(
                f"<tr><td>{endpoint}</td><td>{round(avg_ms, 1)}</td></tr>"
            )
    else:
        lines.append("<tr><td colspan='2'>No API calls recorded</td></tr>")

    lines.extend([
        "</table>",
        "",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w") as fh:
        fh.write("\n".join(lines))


# -----------------------------------------------------------------------------
# Pipeline entry point
# -----------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full ETL pipeline.

    Reads config from environment variables, then:
      1. Extracts entries from the server log.
      2. Transforms them into aggregated metrics.
      3. Loads those metrics into SQLite and writes report.html.
    """
    cfg = get_config()

    print(
        f"Connecting to {cfg['db_host']}:{cfg['db_port']} as {cfg['db_user']}..."
    )

    # Extract
    logs = extract(cfg["log_file"])

    # Transform
    error_counts = transform_errors(logs["errors"])
    api_latency = transform_api_latency(logs["api_calls"])
    active_sessions = transform_active_sessions(logs["users"])

    # Load
    load_to_db(cfg["db_path"], error_counts, api_latency)
    load_to_html("report.html", error_counts, api_latency, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


# -----------------------------------------------------------------------------
# Sample-data bootstrap (for demo / CI only)
# -----------------------------------------------------------------------------


def ensure_sample_log(log_file: str) -> None:
    """Write a minimal sample log if the log file does not exist.

    This lets the pipeline run out-of-the-box for demonstration purposes.
    It is NOT part of the normal pipeline run.
    """
    if os.path.exists(log_file):
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]

    with open(log_file, "w") as fh:
        fh.write("\n".join(sample_lines) + "\n")


if __name__ == "__main__":
    cfg = get_config()
    ensure_sample_log(cfg["log_file"])
    run_pipeline()
