"""
Log processing pipeline that extracts, transforms, and loads server metrics.

Generates an HTML report from server log files with error summaries,
API latency statistics, and active session counts.

Environment Variables:
    LOG_FILE: Path to the server log file (default: server.log)
    DB_PATH: Path to the SQLite database file (default: metrics.db)
    DB_HOST: Database host address (default: localhost)
    DB_PORT: Database port number (default: 5432)
    DB_USER: Database username (default: admin)
    DB_PASS: Database password (default: password123)
    REPORT_PATH: Output path for the HTML report (default: report.html)
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, NamedTuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    """Holds all pipeline configuration from environment variables."""

    LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
    DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
    DB_USER: str = os.environ.get("DB_USER", "admin")
    DB_PASS: str = os.environ.get("DB_PASS", "password123")
    REPORT_PATH: str = os.environ.get("REPORT_PATH", "report.html")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ErrorEntry(NamedTuple):
    """A single error message with its timestamp."""
    timestamp: str
    message: str


class APIcall(NamedTuple):
    """A single API call record with endpoint and latency."""
    timestamp: str
    endpoint: str
    latency_ms: int


class UserAction(NamedTuple):
    """A single user action (login/logout) record."""
    timestamp: str
    user_id: str
    action: str


# ---------------------------------------------------------------------------
# Log line patterns (compiled once)
# ---------------------------------------------------------------------------

_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_ERROR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$")
_INFO_USER_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.+)$"
)
_INFO_API_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"
)
_WARN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.+)$")


# ---------------------------------------------------------------------------
# EXTRACT: Parse log file
# ---------------------------------------------------------------------------

def parse_log_file(log_path: str) -> tuple:
    """
    Read and parse a server log file, extracting errors, API calls, and user actions.

    Args:
        log_path: Path to the log file to parse.

    Returns:
        A tuple of (errors, api_calls, user_actions) where each is a list
        of the corresponding NamedTuple records.
    """
    errors: List[ErrorEntry] = []
    api_calls: List[APIcall] = []
    user_actions: List[UserAction] = []

    if not os.path.exists(log_path):
        print(f"Warning: Log file '{log_path}' not found. Proceeding with empty data.")
        return errors, api_calls, user_actions

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Try each pattern in order of specificity
            if (match := _ERROR_RE.match(line)) is not None:
                timestamp, message = match.groups()
                errors.append(ErrorEntry(timestamp=timestamp, message=message))

            elif (match := _INFO_API_RE.match(line)) is not None:
                timestamp, endpoint, latency = match.groups()
                api_calls.append(APIcall(
                    timestamp=timestamp,
                    endpoint=endpoint,
                    latency_ms=int(latency)
                ))

            elif (match := _INFO_USER_RE.match(line)) is not None:
                timestamp, user_id, action = match.groups()
                user_actions.append(UserAction(
                    timestamp=timestamp,
                    user_id=user_id,
                    action=action
                ))

            elif (match := _WARN_RE.match(line)) is not None:
                # Treat warnings as errors for reporting purposes
                timestamp, message = match.groups()
                errors.append(ErrorEntry(timestamp=timestamp, message=f"[WARN] {message}"))

    return errors, api_calls, user_actions


# ---------------------------------------------------------------------------
# TRANSFORM: Aggregate data
# ---------------------------------------------------------------------------

def aggregate_errors(errors: List[ErrorEntry]) -> Dict[str, int]:
    """
    Count occurrences of each unique error message.

    Args:
        errors: List of ErrorEntry records.

    Returns:
        Dictionary mapping error message to occurrence count.
    """
    counts: Dict[str, int] = {}
    for entry in errors:
        counts[entry.message] = counts.get(entry.message, 0) + 1
    return counts


def aggregate_api_metrics(api_calls: List[APIcall]) -> Dict[str, List[int]]:
    """
    Group API calls by endpoint and collect latency values.

    Args:
        api_calls: List of APIcall records.

    Returns:
        Dictionary mapping endpoint to list of latency values (in ms).
    """
    metrics: Dict[str, List[int]] = {}
    for call in api_calls:
        metrics.setdefault(call.endpoint, []).append(call.latency_ms)
    return metrics


def track_active_sessions(user_actions: List[UserAction]) -> int:
    """
    Determine the number of currently active user sessions.

    A user is considered active if they have logged in but not yet logged out.
    Users with multiple logins count once (net active).

    Args:
        user_actions: List of UserAction records in chronological order.

    Returns:
        Number of currently active sessions.
    """
    active_users: Dict[str, bool] = {}

    for action in user_actions:
        if "logged in" in action.action:
            active_users[action.user_id] = True
        elif "logged out" in action.action:
            active_users.pop(action.user_id, None)

    return len(active_users)


# ---------------------------------------------------------------------------
# LOAD: Write to database and generate report
# ---------------------------------------------------------------------------

def write_to_database(
    db_path: str,
    errors: Dict[str, int],
    api_metrics: Dict[str, List[int]],
) -> None:
    """
    Persist error counts and API latency aggregates to an SQLite database.

    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        errors: Dictionary of error message -> count.
        api_metrics: Dictionary of endpoint -> list of latency values.
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

    # Parameterized INSERT for errors
    for message, count in errors.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, message, count)
        )

    # Parameterized INSERT for API metrics
    for endpoint, latencies in api_metrics.items():
        avg_ms = sum(latencies) / len(latencies) if latencies else 0.0
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms)
        )

    conn.commit()
    conn.close()


def generate_html_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_metrics: Dict[str, List[int]],
    active_session_count: int,
) -> None:
    """
    Generate an HTML report with error summary, API latency table, and active sessions.

    Args:
        report_path: Path where the HTML file will be written.
        error_counts: Dictionary of error message -> count.
        api_metrics: Dictionary of endpoint -> list of latency values.
        active_session_count: Number of currently active user sessions.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_parts: List[str] = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"<title>System Report — {now}</title>",
        "</head>",
        "<body>",
        f"<h1>System Report — {now}</h1>",
        "",
        "<h2>Error Summary</h2>",
        "<ul>",
    ]

    if error_counts:
        for message, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            html_parts.append(
                f'<li><b>{message}</b>: {count} occurrence{"s" if count != 1 else ""}</li>'
            )
    else:
        html_parts.append("<li>No errors recorded.</li>")

    html_parts.extend([
        "</ul>",
        "",
        "<h2>API Latency</h2>",
        "<table border='1' cellpadding='4' cellspacing='0'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th><th>Call Count</th></tr>",
    ])

    if api_metrics:
        for endpoint, latencies in sorted(api_metrics.items()):
            avg_ms = sum(latencies) / len(latencies)
            call_count = len(latencies)
            html_parts.append(
                f"<tr><td>{endpoint}</td><td>{avg_ms:.1f}</td><td>{call_count}</td></tr>"
            )
    else:
        html_parts.append("<tr><td colspan='3'>No API calls recorded.</td></tr>")

    html_parts.extend([
        "</table>",
        "",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w") as f:
        f.write("\n".join(html_parts))


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract log data, transform it, and load results.

    Reads configuration from environment variables, parses the server log,
    aggregates metrics, writes to the database, and generates report.html.
    """
    config = Config()

    print(
        f"Connecting to {config.DB_HOST}:{config.DB_PORT} as {config.DB_USER}..."
    )
    print(f"Reading log file: {config.LOG_FILE}")

    # EXTRACT
    errors, api_calls, user_actions = parse_log_file(config.LOG_FILE)

    # TRANSFORM
    error_counts = aggregate_errors(errors)
    api_metrics = aggregate_api_metrics(api_calls)
    active_sessions = track_active_sessions(user_actions)

    # LOAD
    write_to_database(config.DB_PATH, error_counts, api_metrics)
    generate_html_report(
        config.REPORT_PATH,
        error_counts,
        api_metrics,
        active_sessions,
    )

    print(f"Report written to: {config.REPORT_PATH}")
    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bootstrap a sample log file if none exists (for testing/demo)
    if not os.path.exists(Config.LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        with open(Config.LOG_FILE, "w") as f:
            f.write("\n".join(sample_lines) + "\n")

    run_pipeline()
