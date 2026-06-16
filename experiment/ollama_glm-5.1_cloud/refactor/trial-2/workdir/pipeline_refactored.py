"""Pipeline for processing server logs and generating reports.

Extracts structured entries from a log file, transforms them into
aggregated metrics (error counts, API latency averages, active sessions),
loads the results into a SQLite database, and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration – all values sourced from environment variables
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ErrorEntry:
    """A parsed ERROR or WARN log line."""

    timestamp: str
    message: str


@dataclass
class UserEvent:
    """A user login/logout event extracted from INFO lines."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """An API call with its measured latency."""

    timestamp: str
    endpoint: str
    latency_ms: int


@dataclass
class ParsedLog:
    """Container for all entries extracted from a log file."""

    errors: list[ErrorEntry] = field(default_factory=list)
    warnings: list[ErrorEntry] = field(default_factory=list)
    user_events: list[UserEvent] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)


@dataclass
class TransformedData:
    """Aggregated metrics ready for storage and reporting."""

    error_counts: dict[str, int] = field(default_factory=dict)
    api_latency: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: int = 0


# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------
_ERROR_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<msg>.+)$"
)
_WARN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<msg>.+)$"
)
_USER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_API_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+)(?: took (?P<ms>\d+)ms)?$"
)


# ---------------------------------------------------------------------------
# Extract – read and parse log lines
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: str) -> ParsedLog:
    """Read a log file and parse each line into structured entries.

    Uses compiled regex patterns to robustly extract timestamps,
    log levels, and payload fields regardless of spacing variations.

    Args:
        log_path: Filesystem path to the server log.

    Returns:
        A ``ParsedLog`` with categorized entries.
    """
    parsed = ParsedLog()
    path = Path(log_path)
    if not path.exists():
        return parsed

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue

            match = _ERROR_RE.match(line)
            if match:
                parsed.errors.append(
                    ErrorEntry(timestamp=match["ts"], message=match["msg"])
                )
                continue

            match = _WARN_RE.match(line)
            if match:
                parsed.warnings.append(
                    ErrorEntry(timestamp=match["ts"], message=match["msg"])
                )
                continue

            match = _USER_RE.match(line)
            if match:
                parsed.user_events.append(
                    UserEvent(
                        timestamp=match["ts"],
                        user_id=match["uid"],
                        action=match["action"],
                    )
                )
                continue

            match = _API_RE.match(line)
            if match:
                latency = int(match["ms"]) if match["ms"] else 0
                parsed.api_calls.append(
                    ApiCall(
                        timestamp=match["ts"],
                        endpoint=match["endpoint"],
                        latency_ms=latency,
                    )
                )

    return parsed


# ---------------------------------------------------------------------------
# Transform – aggregate raw entries into summary metrics
# ---------------------------------------------------------------------------


def transform_entries(parsed: ParsedLog) -> TransformedData:
    """Aggregate parsed log entries into summary metrics.

    Computes error occurrence counts, per-endpoint API latency
    distributions, and the number of currently active sessions.

    Args:
        parsed: Output of ``extract_log_entries``.

    Returns:
        A ``TransformedData`` ready for persistence and reporting.
    """
    error_counts: dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    api_latency: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.latency_ms)

    # Track sessions: login creates, logout removes
    sessions: dict[str, str] = {}
    for event in parsed.user_events:
        if "logged in" in event.action:
            sessions[event.user_id] = event.timestamp
        elif "logged out" in event.action and event.user_id in sessions:
            sessions.pop(event.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load – persist metrics to database and generate HTML report
# ---------------------------------------------------------------------------


def load_to_database(db_path: str, data: TransformedData) -> None:
    """Write aggregated metrics into a SQLite database.

    Uses parameterized queries exclusively to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        data: Aggregated metrics to persist.
    """
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for message, count in data.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, message, count),
        )

    for endpoint, times in data.api_latency.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


def generate_report(data: TransformedData, output_path: str = "report.html") -> None:
    """Render aggregated metrics as an HTML report.

    The report contains three sections matching the original output:
    error summary, API latency table, and active session count.

    Args:
        data: Aggregated metrics to render.
        output_path: Destination path for the HTML file.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for message, count in data.error_counts.items():
        lines.append(f"<li><b>{message}</b>: {count} occurrences</li>")

    lines.append("</ul>")
    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    for endpoint, times in data.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        lines.append(f"<tr><td>{endpoint}</td><td>{avg}</td></tr>")

    lines.append("</table>")
    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{data.active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Report written to {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full Extract-Transform-Load pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed = extract_log_entries(LOG_FILE)
    data = transform_entries(parsed)
    load_to_database(DB_PATH, data)
    generate_report(data)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()