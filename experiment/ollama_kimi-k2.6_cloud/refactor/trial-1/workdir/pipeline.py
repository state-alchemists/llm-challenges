"""Server log pipeline: extract, transform, load, and report."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Load configuration from the process environment.

    Falls back to the legacy hard-coded defaults so the script stays
    runnable out-of-the-box when no environment overrides are supplied.
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ErrorEntry:
    """An ERROR-level log event."""

    dt: str
    message: str


@dataclass(frozen=True)
class WarnEntry:
    """A WARN-level log event."""

    dt: str
    message: str


@dataclass(frozen=True)
class UserEntry:
    """An INFO-level user action."""

    dt: str
    user_id: str
    action: str


@dataclass(frozen=True)
class ApiEntry:
    """An INFO-level API call with measured latency."""

    dt: str
    endpoint: str
    duration_ms: int


LogEntry = Union[ErrorEntry, WarnEntry, UserEntry, ApiEntry]


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<message>.+)$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")

_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<ms>\d+)ms$")


def _parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse a single log line into a structured entry.

    Args:
        line: Raw line read from the log file.

    Returns:
        A typed log entry, or ``None`` when the line is blank,
        malformed, or does not match a known pattern.
    """
    stripped = line.strip()
    if not stripped:
        return None

    match = _LOG_LINE_RE.match(stripped)
    if not match:
        return None

    dt = f"{match.group('date')} {match.group('time')}"
    level = match.group("level")
    message = match.group("message")

    if level == "ERROR":
        return ErrorEntry(dt=dt, message=message)

    if level == "WARN":
        return WarnEntry(dt=dt, message=message)

    if level == "INFO":
        user_match = _USER_RE.match(message)
        if user_match:
            return UserEntry(
                dt=dt,
                user_id=user_match.group("user_id"),
                action=user_match.group("action"),
            )

        api_match = _API_RE.match(message)
        if api_match:
            return ApiEntry(
                dt=dt,
                endpoint=api_match.group("endpoint"),
                duration_ms=int(api_match.group("ms")),
            )

    return None


def extract(log_file: str) -> List[LogEntry]:
    """Read and parse the server log file.

    Args:
        log_file: Path to the log file to ingest.

    Returns:
        Ordered list of structured log entries.
    """
    path = Path(log_file)
    if not path.exists():
        return []

    entries: List[LogEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            entry = _parse_log_line(raw)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransformedData:
    """Aggregated data ready for the load phase."""

    error_counts: Dict[str, int]
    api_latencies: Dict[str, List[int]]
    active_sessions: int


def transform(entries: List[LogEntry]) -> TransformedData:
    """Aggregate raw log entries into metrics and session state.

    Args:
        entries: Structured entries produced by :func:`extract`.

    Returns:
        Error frequency map, per-endpoint latency lists, and the
        number of currently-active user sessions.
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in entries:
        if isinstance(entry, ErrorEntry):
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

        elif isinstance(entry, ApiEntry):
            api_latencies.setdefault(entry.endpoint, []).append(entry.duration_ms)

        elif isinstance(entry, UserEntry):
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.dt
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)

        # WarnEntry is intentionally ignored for reporting, mirroring the
        # original behaviour.

    return TransformedData(
        error_counts=error_counts,
        api_latencies=api_latencies,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _init_database(conn: sqlite3.Connection) -> None:
    """Create required tables if they do not already exist."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    cur.close()


def _persist_errors(conn: sqlite3.Connection, error_counts: Dict[str, int]) -> None:
    """Insert aggregated error rows using a parameterized query."""
    now = str(datetime.datetime.now())
    cur = conn.cursor()
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )
    cur.close()


def _persist_api_metrics(
    conn: sqlite3.Connection, api_latencies: Dict[str, List[int]]
) -> None:
    """Insert aggregated API-latency rows using a parameterized query."""
    now = str(datetime.datetime.now())
    cur = conn.cursor()
    for endpoint, times in api_latencies.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )
    cur.close()


def _generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """Render the HTML system report to *output_path*.

    The markup mirrors the original report so downstream consumers
    see identical information in the same structure.
    """
    lines = [
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

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def load(
    config: Config,
    data: TransformedData,
    output_path: str = "report.html",
) -> None:
    """Persist transformed data to the database and write the HTML report.

    Args:
        config: Runtime configuration (paths, credentials).
        data: Aggregated metrics from the transform phase.
        output_path: Destination path for the generated report.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    _init_database(conn)
    _persist_errors(conn, data.error_counts)
    _persist_api_metrics(conn, data.api_latencies)
    conn.commit()
    conn.close()

    _generate_report(
        data.error_counts,
        data.api_latencies,
        data.active_sessions,
        output_path,
    )

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _seed_sample_log(log_file: str) -> None:
    """Create a sample log file if one does not already exist."""
    path = Path(log_file)
    if path.exists():
        return

    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    """Pipeline entry point: ETL then report generation."""
    config = load_config()
    _seed_sample_log(config.log_file)
    entries = extract(config.log_file)
    data = transform(entries)
    load(config, data, output_path="report.html")


if __name__ == "__main__":
    main()
