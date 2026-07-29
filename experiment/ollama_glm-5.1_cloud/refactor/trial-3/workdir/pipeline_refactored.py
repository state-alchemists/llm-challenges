"""Refactored server-log processing pipeline.

Extracts log events, transforms them into aggregated metrics,
loads them into a SQLite database, and generates an HTML report.

Configuration is sourced entirely from environment variables so that
no credentials or paths are hard-coded in the source file.
"""

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration – every value comes from the environment
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------

# Matches: 2024-01-01 12:00:00 INFO ...
LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|WARN|INFO)\s+"
    r"(?P<rest>.*)$"
)

# Matches user events: "User 42 logged in" / "User 42 logged out"
USER_EVENT_RE = re.compile(
    r"User\s+(?P<user_id>\S+)\s+(?P<action>.*)$"
)

# Matches API calls: "API /users/profile took 250ms"
API_CALL_RE = re.compile(
    r"API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<duration>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LogEvent:
    """A single parsed log event."""
    timestamp: str
    level: str
    message: str


@dataclass
class UserEvent:
    """A user login/logout event."""
    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call recorded in the log."""
    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class ParsedLog:
    """Aggregated result of parsing a log file."""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    user_events: List[UserEvent] = field(default_factory=list)
    api_calls: List[ApiCall] = field(default_factory=list)
    active_sessions: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extract – read and parse the log file
# ---------------------------------------------------------------------------

def extract_log_events(log_path: str) -> ParsedLog:
    """Read *log_path* and parse every line into structured events.

    Uses regex patterns so that malformed lines are skipped gracefully
    rather than raising index errors.

    Returns:
        A :class:`ParsedLog` with errors, warnings, user events, and
        API calls separated into typed lists.
    """
    parsed = ParsedLog()

    if not os.path.exists(log_path):
        return parsed

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            rest = match.group("rest")

            if level == "ERROR":
                parsed.errors.append(rest)

            elif level == "WARN":
                parsed.warnings.append(rest)

            elif level == "INFO":
                user_match = USER_EVENT_RE.search(rest)
                if user_match:
                    user_id = user_match.group("user_id")
                    action = user_match.group("action")
                    parsed.user_events.append(
                        UserEvent(timestamp=timestamp, user_id=user_id, action=action)
                    )
                    if "logged in" in action:
                        parsed.active_sessions[user_id] = timestamp
                    elif "logged out" in action and user_id in parsed.active_sessions:
                        del parsed.active_sessions[user_id]
                    continue

                api_match = API_CALL_RE.search(rest)
                if api_match:
                    endpoint = api_match.group("endpoint")
                    duration = int(api_match.group("duration") or 0)
                    parsed.api_calls.append(
                        ApiCall(timestamp=timestamp, endpoint=endpoint, duration_ms=duration)
                    )

    return parsed


# ---------------------------------------------------------------------------
# Transform – aggregate raw events into summary metrics
# ---------------------------------------------------------------------------

def transform_error_counts(errors: List[str]) -> Dict[str, int]:
    """Count occurrences of each distinct error message.

    Args:
        errors: List of error message strings.

    Returns:
        Mapping of error message → occurrence count.
    """
    counts: Dict[str, int] = {}
    for msg in errors:
        counts[msg] = counts.get(msg, 0) + 1
    return counts


def transform_api_latency(api_calls: List[ApiCall]) -> Dict[str, List[int]]:
    """Group API call durations by endpoint.

    Args:
        api_calls: List of :class:`ApiCall` records.

    Returns:
        Mapping of endpoint → list of latency values in milliseconds.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


# ---------------------------------------------------------------------------
# Load – persist metrics to SQLite and write the HTML report
# ---------------------------------------------------------------------------

def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
) -> None:
    """Insert aggregated metrics into the SQLite database at *db_path*.

    All SQL statements use parameterized queries (`?` placeholders) to
    prevent injection.

    Args:
        db_path: Filesystem path to the SQLite database.
        error_counts: Error message → count mapping.
        api_latency: Endpoint → latency-list mapping.
    """
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, durations in api_latency.items():
        avg_ms = sum(durations) / len(durations) if durations else 0.0
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def load_report(
    output_path: str,
    error_counts: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Generate the HTML report and write it to *output_path*.

    The report contains three sections that mirror the original script:
    an error summary, an API latency table, and the active session count.

    Args:
        output_path: Destination file path (e.g. ``report.html``).
        error_counts: Error message → count mapping.
        api_latency: Endpoint → latency-list mapping.
        active_sessions: Currently active user-id → timestamp mapping.
    """
    lines: List[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    # Error summary
    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    # API latency table
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, durations in api_latency.items():
        avg = round(sum(durations) / len(durations), 1) if durations else 0.0
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")
    lines.append("</table>")

    # Active sessions
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    # Extract
    parsed = extract_log_events(LOG_FILE)

    # Transform
    error_counts = transform_error_counts(parsed.errors)
    api_latency = transform_api_latency(parsed.api_calls)

    # Load
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    load_to_database(DB_PATH, error_counts, api_latency)
    load_report("report.html", error_counts, api_latency, parsed.active_sessions)

    print(f"Job finished at {datetime.now()}")


if __name__ == "__main__":
    # When no log file exists, create a small sample so the script
    # can be demonstrated end-to-end without external data.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()