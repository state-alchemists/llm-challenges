"""
Pipeline: Extract, Transform, Load system metrics from server logs.

Reads server logs, aggregates error counts and API latency statistics,
stores results in SQLite, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedError:
    """An error entry extracted from a log line."""
    timestamp: str
    message: str


@dataclass
class ParsedApiCall:
    """An API latency entry extracted from a log line."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedUserAction:
    """A user session action extracted from a log line."""
    timestamp: str
    user_id: str
    action: str  # "logged in" or "logged out"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Log format: 2024-01-01 12:00:00 LEVEL Message
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.*)$"
)

# API call: INFO ... API /endpoint/path took Nms
API_CALL_RE = re.compile(r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms")

# User action: INFO ... User <id> <action>
USER_ACTION_RE = re.compile(r"User (?P<user_id>\S+) (?P<action>logged in|logged out)")


# ---------------------------------------------------------------------------
# Extract stage
# ---------------------------------------------------------------------------


def read_log_file(path: str) -> list[str]:
    """
    Read the log file and return its lines.

    Args:
        path: Path to the server log file.

    Returns:
        List of raw log lines (including trailing newline).
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        return fh.readlines()


def parse_log_line(line: str) -> dict | None:
    """
    Parse a single log line into a typed dict.

    Returns one of:
        - {"kind": "error", **ParsedError}
        - {"kind": "api_call", **ParsedApiCall}
        - {"kind": "user_action", **ParsedUserAction}
        - {"kind": "warn", "timestamp": str, "message": str}
        - None (unrecognized line)
    """
    stripped = line.strip()
    match = LOG_LINE_RE.match(stripped)
    if not match:
        return None

    timestamp = match.group("timestamp")
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return {"kind": "error", "timestamp": timestamp, "message": message}

    if level == "WARN":
        return {"kind": "warn", "timestamp": timestamp, "message": message}

    if level == "INFO":
        api_match = API_CALL_RE.search(message)
        if api_match:
            return {
                "kind": "api_call",
                "timestamp": timestamp,
                "endpoint": api_match.group("endpoint"),
                "duration_ms": int(api_match.group("ms")),
            }

        user_match = USER_ACTION_RE.search(message)
        if user_match:
            return {
                "kind": "user_action",
                "timestamp": timestamp,
                "user_id": user_match.group("user_id"),
                "action": user_match.group("action"),
            }

    return None


def extract(log_path: str) -> tuple[list[ParsedError], list[ParsedApiCall], list[ParsedUserAction]]:
    """
    Extract structured data from the log file.

    Args:
        log_path: Path to the server log file.

    Returns:
        Tuple of (errors, api_calls, user_actions).
    """
    lines = read_log_file(log_path)
    errors: list[ParsedError] = []
    api_calls: list[ParsedApiCall] = []
    user_actions: list[ParsedUserAction] = []

    for line in lines:
        parsed = parse_log_line(line)
        if parsed is None:
            continue

        kind = parsed.pop("kind")

        if kind == "error":
            errors.append(ParsedError(**parsed))
        elif kind == "api_call":
            api_calls.append(ParsedApiCall(**parsed))
        elif kind == "user_action":
            user_actions.append(ParsedUserAction(**parsed))
        # "warn" entries are not persisted; they are not in the original output

    return errors, api_calls, user_actions


# ---------------------------------------------------------------------------
# Transform stage
# ---------------------------------------------------------------------------


def compute_error_counts(errors: list[ParsedError]) -> dict[str, int]:
    """
    Aggregate error messages into counts.

    Args:
        errors: List of parsed error entries.

    Returns:
        Dict mapping error message -> occurrence count.
    """
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def compute_api_latency(api_calls: list[ParsedApiCall]) -> dict[str, list[int]]:
    """
    Group API calls by endpoint and collect durations.

    Args:
        api_calls: List of parsed API call entries.

    Returns:
        Dict mapping endpoint -> list of duration_ms values.
    """
    by_endpoint: dict[str, list[int]] = {}
    for call in api_calls:
        by_endpoint.setdefault(call.endpoint, []).append(call.duration_ms)
    return by_endpoint


def compute_active_sessions(user_actions: list[ParsedUserAction]) -> int:
    """
    Count currently active sessions by processing login/logout actions in order.

    Args:
        user_actions: List of parsed user action entries, in chronological order.

    Returns:
        Number of users still logged in at the end of the log.
    """
    sessions: set[str] = set()
    for action in user_actions:
        if action.action == "logged in":
            sessions.add(action.user_id)
        elif action.action == "logged out":
            sessions.discard(action.user_id)
    return len(sessions)


def transform(
    errors: list[ParsedError],
    api_calls: list[ParsedApiCall],
    user_actions: list[ParsedUserAction],
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """
    Transform extracted data into aggregated metrics.

    Returns:
        Tuple of (error_counts, api_latency_by_endpoint, active_session_count).
    """
    return (
        compute_error_counts(errors),
        compute_api_latency(api_calls),
        compute_active_sessions(user_actions),
    )


# ---------------------------------------------------------------------------
# Load stage
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """
    Create the required tables if they do not exist.

    Args:
        conn: Open SQLite connection.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )


def write_errors(conn: sqlite3.Connection, error_counts: dict[str, int]) -> None:
    """
    Insert aggregated error counts into the database using parameterized queries.

    Args:
        conn: Open SQLite connection.
        error_counts: Error message -> count mapping.
    """
    now = datetime.datetime.now()
    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now.isoformat(), msg, count),
        )


def write_api_metrics(
    conn: sqlite3.Connection,
    latency_by_endpoint: dict[str, list[int]],
) -> None:
    """
    Insert averaged API latency per endpoint using parameterized queries.

    Args:
        conn: Open SQLite connection.
        latency_by_endpoint: Endpoint -> list of duration_ms values.
    """
    now = datetime.datetime.now()
    for ep, durations in latency_by_endpoint.items():
        avg = sum(durations) / len(durations)
        conn.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now.isoformat(), ep, avg),
        )


def generate_html_report(
    error_counts: dict[str, int],
    latency_by_endpoint: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """
    Render the HTML report with the same structure as the original.

    Args:
        error_counts: Error message -> count mapping.
        latency_by_endpoint: Endpoint -> list of duration_ms values.
        active_sessions: Number of currently active sessions.

    Returns:
        Complete HTML document as a string.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, durations in latency_by_endpoint.items():
        avg = sum(durations) / len(durations)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def load(
    db_path: str,
    error_counts: dict[str, int],
    latency_by_endpoint: dict[str, list[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """
    Persist metrics to SQLite and write the HTML report.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Error message -> count mapping.
        latency_by_endpoint: Endpoint -> list of duration_ms values.
        active_sessions: Number of currently active sessions.
        output_path: Destination path for the HTML report.
    """
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        write_errors(conn, error_counts)
        write_api_metrics(conn, latency_by_endpoint)
        conn.commit()
    finally:
        conn.close()

    html = generate_html_report(error_counts, latency_by_endpoint, active_sessions)
    with open(output_path, "w") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract → transform → load.

    Reads configuration from environment variables (or their defaults),
    processes the log file, updates the database, and writes report.html.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    errors, api_calls, user_actions = extract(LOG_FILE)
    error_counts, latency_by_endpoint, active_sessions = transform(
        errors, api_calls, user_actions
    )
    load(DB_PATH, error_counts, latency_by_endpoint, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a sample log when none exists (mirrors original behaviour)
    if not os.path.exists(LOG_FILE):
        sample_log_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in\n",
            "2024-01-01 12:05:00 ERROR Database timeout\n",
            "2024-01-01 12:05:05 ERROR Database timeout\n",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
        ]
        with open(LOG_FILE, "w") as f:
            f.writelines(sample_log_lines)

    run_pipeline()
