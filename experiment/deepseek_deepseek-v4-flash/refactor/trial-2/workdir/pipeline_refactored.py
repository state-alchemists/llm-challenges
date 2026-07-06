"""Pipeline for processing server logs into structured reports.

Follows Extract -> Transform -> Load pattern:

- **Extract:** parse log lines into typed dataclass entries using regex
- **Transform:** aggregate error counts, API latency averages, track sessions
- **Load:** persist aggregates to SQLite (parameterised queries) and produce
  ``report.html``
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration (all from environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("PIPELINE_DB_PATH", "metrics.db")
LOG_PATH: str = os.environ.get("PIPELINE_LOG_PATH", "server.log")
OUTPUT_PATH: str = os.environ.get("PIPELINE_OUTPUT_PATH", "report.html")

# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """Base record for a single parsed log line."""

    timestamp: str
    level: str
    raw: str


@dataclass
class ErrorEntry(LogEntry):
    """An ERROR-level log line carrying a free-form message."""

    message: str


@dataclass
class WarnEntry(LogEntry):
    """A WARN-level log line carrying a free-form message."""

    message: str


@dataclass
class UserEntry(LogEntry):
    """An INFO-level user event (login / logout / action)."""

    user_id: str
    action: str


@dataclass
class ApiEntry(LogEntry):
    """An INFO-level API latency measurement."""

    endpoint: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Extract — parse log file into structured entries
# ---------------------------------------------------------------------------

# Ordered: more specific patterns first so they take precedence over the
# generic ``ERROR`` / ``WARN`` fallbacks.
_LOG_PATTERNS: List[re.Pattern[str]] = [
    re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"ERROR (?P<msg>.+)$"
    ),
    re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"WARN (?P<msg>.+)$"
    ),
    re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"INFO User (?P<uid>\d+) (?P<action>.+)$"
    ),
    re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"INFO API (?P<endpoint>\S+) took (?P<dur>\d+)ms$"
    ),
]


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single server-log line into the appropriate ``LogEntry``.

    Supports ``ERROR``, ``WARN``, ``INFO User`` (login/logout), and
    ``INFO API`` (latency) formats. Returns **None** for blank or
    unrecognised lines so callers can skip them transparently.
    """
    stripped = line.strip()
    if not stripped:
        return None

    # ERROR
    m = _LOG_PATTERNS[0].match(stripped)
    if m:
        return ErrorEntry(
            timestamp=m.group("ts"),
            level="ERROR",
            raw=stripped,
            message=m.group("msg"),
        )

    # WARN
    m = _LOG_PATTERNS[1].match(stripped)
    if m:
        return WarnEntry(
            timestamp=m.group("ts"),
            level="WARN",
            raw=stripped,
            message=m.group("msg"),
        )

    # INFO User (login/logout/action)
    m = _LOG_PATTERNS[2].match(stripped)
    if m:
        return UserEntry(
            timestamp=m.group("ts"),
            level="INFO",
            raw=stripped,
            user_id=m.group("uid"),
            action=m.group("action"),
        )

    # INFO API (endpoint latency)
    m = _LOG_PATTERNS[3].match(stripped)
    if m:
        return ApiEntry(
            timestamp=m.group("ts"),
            level="INFO",
            raw=stripped,
            endpoint=m.group("endpoint"),
            duration_ms=int(m.group("dur")),
        )

    # Minimal fallback for lines that look timestamped but don't match
    # any known pattern — keeps them visible rather than silently dropping.
    parts = stripped.split(" ", 2)
    if len(parts) >= 3:
        return LogEntry(
            timestamp=f"{parts[0]} {parts[1]}",
            level=parts[2].split(" ")[0],
            raw=stripped,
        )

    return None


def extract_logs(log_path: str) -> List[LogEntry]:
    """Read *log_path* and return a list of parsed ``LogEntry`` objects.

    Non-existent files return an empty list silently.  Lines that cannot
    be parsed are skipped.
    """
    if not os.path.exists(log_path):
        return []

    entries: List[LogEntry] = []
    with open(log_path, "r") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform — derive metrics from parsed entries
# ---------------------------------------------------------------------------


def compute_error_counts(entries: List[LogEntry]) -> Dict[str, int]:
    """Count occurrences of each distinct error message."""
    counts: Dict[str, int] = {}
    for e in entries:
        if isinstance(e, ErrorEntry):
            counts[e.message] = counts.get(e.message, 0) + 1
    return counts


def compute_api_stats(entries: List[LogEntry]) -> Dict[str, float]:
    """Compute average latency (ms) for each API endpoint."""
    durations: Dict[str, List[int]] = {}
    for e in entries:
        if isinstance(e, ApiEntry):
            durations.setdefault(e.endpoint, []).append(e.duration_ms)
    return {ep: sum(times) / len(times) for ep, times in durations.items()}


def count_active_sessions(entries: List[LogEntry]) -> int:
    """Return the number of users currently logged in.

    Tracks login/logout events in the order they appear so that a user
    who logs in and then out is only counted as active between those
    two events.
    """
    sessions: Dict[str, str] = {}
    for e in entries:
        if isinstance(e, UserEntry):
            uid = e.user_id
            if "logged in" in e.action:
                sessions[uid] = e.timestamp
            elif "logged out" in e.action and uid in sessions:
                del sessions[uid]
    return len(sessions)


# ---------------------------------------------------------------------------
# Load — persist aggregated metrics and generate the HTML report
# ---------------------------------------------------------------------------


def _init_database(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection, creating tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors"
        " (dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics"
        " (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    return conn


def save_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_stats: Dict[str, float],
) -> None:
    """Write error and API-latency aggregates to SQLite.

    Uses **parameterised queries** so user-derived content is never
    interpolated directly into SQL text.
    """
    conn = _init_database(db_path)
    now = datetime.datetime.now().isoformat()

    with conn:
        for msg, count in error_counts.items():
            conn.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )
        for ep, avg_ms in api_stats.items():
            conn.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms)"
                " VALUES (?, ?, ?)",
                (now, ep, avg_ms),
            )


def generate_html_report(
    error_counts: Dict[str, int],
    api_stats: Dict[str, float],
    active_sessions: int,
) -> str:
    """Build the complete HTML report as a single string.

    Sections:
      1. Error summary (message -> occurrence count)
      2. API latency table (endpoint -> average ms)
      3. Active session count
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg_ms in api_stats.items():
        lines.append(
            f"<tr><td>{ep}</td><td>{round(avg_ms, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_sessions} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate_seed_data(log_path: str) -> None:
    """Write a sample log file when none exists (first-run convenience)."""
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(log_path, "w") as fh:
        fh.write("\n".join(sample_lines) + "\n")


def main() -> None:
    """Orchestrate the full ETL pipeline.

    Steps
    -----
    1. Seed ``LOG_PATH`` if it does not exist (sample data).
    2. **Extract** — parse all log lines into typed entries.
    3. **Transform** — compute error counts, API latency, active sessions.
    4. **Load** — write aggregates to SQLite, then write ``report.html``.
    """
    if not os.path.exists(LOG_PATH):
        generate_seed_data(LOG_PATH)

    entries = extract_logs(LOG_PATH)

    error_counts = compute_error_counts(entries)
    api_stats = compute_api_stats(entries)
    active_sessions = count_active_sessions(entries)

    save_to_database(DB_PATH, error_counts, api_stats)

    html = generate_html_report(error_counts, api_stats, active_sessions)
    with open(OUTPUT_PATH, "w") as fh:
        fh.write(html)

    print(f"Pipeline finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
