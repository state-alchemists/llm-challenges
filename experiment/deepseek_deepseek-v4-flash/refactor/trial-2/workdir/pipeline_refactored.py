"""Server log processing pipeline with Extract → Transform → Load."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str = "metrics.db"
    log_file: str = "server.log"


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """A parsed ERROR-level log line."""

    timestamp: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEntry:
    """A parsed INFO-level log line recording a user action."""

    timestamp: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEntry:
    """A parsed INFO-level log line recording an API call duration."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """A parsed WARN-level log line."""

    timestamp: str
    message: str


LogEntry = ErrorEntry | UserEntry | ApiEntry | WarnEntry


@dataclass(frozen=True, slots=True)
class RawData:
    """Unaggregated data after the extract phase."""

    errors: list[ErrorEntry]
    api_calls: list[ApiEntry]
    active_sessions: int


@dataclass(frozen=True, slots=True)
class ReportData:
    """Aggregated data ready for loading and reporting."""

    error_counts: dict[str, int]
    endpoint_avg_ms: dict[str, float]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults.

    Reads DB_PATH and LOG_FILE_PATH; falls back to metrics.db and server.log.
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE_PATH", "server.log"),
    )


# ---------------------------------------------------------------------------
# Extract — read and parse log file
# ---------------------------------------------------------------------------

_TIMESTAMP = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a structured entry using regex.

    Recognised formats (matched in order):
        <ts> ERROR <message>
        <ts> INFO User <id> <action>
        <ts> INFO API <endpoint> took <ms>ms
        <ts> WARN <message>

    Returns None for blank or unrecognised lines.
    """
    line = line.strip()
    if not line:
        return None

    # ERROR:  2024-01-01 12:00:00 ERROR Database timeout
    if m := re.match(rf"^({_TIMESTAMP}) ERROR (.+)", line):
        return ErrorEntry(timestamp=m.group(1), message=m.group(2))

    # User:   2024-01-01 12:00:00 INFO User 42 logged in
    if m := re.match(rf"^({_TIMESTAMP}) INFO User (\S+) (.+)", line):
        return UserEntry(
            timestamp=m.group(1), user_id=m.group(2), action=m.group(3)
        )

    # API:    2024-01-01 12:00:00 INFO API /users/profile took 250ms
    if m := re.match(rf"^({_TIMESTAMP}) INFO API (\S+) took (\d+)ms", line):
        return ApiEntry(
            timestamp=m.group(1),
            endpoint=m.group(2),
            duration_ms=int(m.group(3)),
        )

    # WARN:   2024-01-01 12:00:00 WARN Memory usage at 87%
    if m := re.match(rf"^({_TIMESTAMP}) WARN (.+)", line):
        return WarnEntry(timestamp=m.group(1), message=m.group(2))

    return None


def extract(config: Config) -> RawData:
    """Read and parse every line in the log file, tracking user sessions.

    Returns the raw log entries and the count of users still logged in.
    """
    log_path = Path(config.log_file)
    if not log_path.is_file():
        return RawData(errors=[], api_calls=[], active_sessions=0)

    errors: list[ErrorEntry] = []
    api_calls: list[ApiEntry] = []
    sessions: dict[str, str] = {}

    with log_path.open() as f:
        for line in f:
            entry = parse_log_line(line)
            if isinstance(entry, ErrorEntry):
                errors.append(entry)
            elif isinstance(entry, ApiEntry):
                api_calls.append(entry)
            elif isinstance(entry, UserEntry):
                if "logged in" in entry.action:
                    sessions[entry.user_id] = entry.timestamp
                elif entry.user_id in sessions:
                    del sessions[entry.user_id]

    return RawData(
        errors=errors, api_calls=api_calls, active_sessions=len(sessions)
    )


# ---------------------------------------------------------------------------
# Transform — aggregate raw entries into summary statistics
# ---------------------------------------------------------------------------

def transform(raw: RawData) -> ReportData:
    """Aggregate raw log entries into error counts and endpoint latency.

    Groups error entries by message and computes average API duration per
    endpoint.  Entries with no matching records produce empty dicts, not
    None.
    """
    error_counts: dict[str, int] = {}
    for err in raw.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in raw.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.duration_ms)

    endpoint_avg_ms = {
        ep: sum(times) / len(times)
        for ep, times in endpoint_times.items()
    }

    return ReportData(
        error_counts=error_counts, endpoint_avg_ms=endpoint_avg_ms
    )


# ---------------------------------------------------------------------------
# Load — write aggregated data to SQLite
# ---------------------------------------------------------------------------

def load(report: ReportData, config: Config) -> None:
    """Insert aggregated data into SQLite using parameterised queries.

    Creates tables if they do not exist.  Uses ``?`` placeholders for all
    values to prevent SQL injection.
    """
    conn = sqlite3.connect(config.db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = str(datetime.datetime.now())

        for msg, count in report.error_counts.items():
            cur.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg in report.endpoint_avg_ms.items():
            cur.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) "
                "VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report — generate HTML output
# ---------------------------------------------------------------------------

def generate_report(report: ReportData, active_sessions: int) -> str:
    """Build an HTML report summarising errors, API latency, and sessions.

    Produces the same layout as the original pipeline so existing consumers
    of ``report.html`` see identical content.
    """
    parts: list[str] = [
        "<html>\n<head><title>System Report</title></head>\n<body>",
        "<h1>Error Summary</h1>\n<ul>",
    ]
    for msg, count in report.error_counts.items():
        parts.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    parts.append("</ul>\n<h2>API Latency</h2>\n<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in report.endpoint_avg_ms.items():
        parts.append(f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>")
    parts.append("</table>\n<h2>Active Sessions</h2>")
    parts.append(f"<p>{active_sessions} user(s) currently active</p>")
    parts.append("</body>\n</html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _write_sample_log(path: Path) -> None:
    """Write representative sample log data so the pipeline can run."""
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    """Run the full pipeline: extract → transform → load → report."""
    config = load_config()
    if not Path(config.log_file).is_file():
        _write_sample_log(Path(config.log_file))

    raw = extract(config)
    report = transform(raw)
    load(report, config)

    html = generate_report(report, raw.active_sessions)
    Path("report.html").write_text(html)


if __name__ == "__main__":
    main()
