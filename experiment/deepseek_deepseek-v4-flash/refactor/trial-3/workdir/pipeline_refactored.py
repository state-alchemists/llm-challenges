"""Pipeline for processing server logs and generating system reports.

Extracts structured data from log files, transforms it into error summaries
and latency statistics, then loads results into a SQLite database and
produces an HTML report.
"""

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    db_path: str
    log_file_path: str


def load_config() -> Config:
    """Load configuration from environment variables with sensible defaults.

    Expected variables (with defaults):

        PIPELINE_DB_PATH     — path to the SQLite database  (metrics.db)
        PIPELINE_LOG_FILE    — path to the server log file   (server.log)

    Returns:
        A Config dataclass populated from the environment.
    """
    return Config(
        db_path=os.environ.get("PIPELINE_DB_PATH", "metrics.db"),
        log_file_path=os.environ.get("PIPELINE_LOG_FILE", "server.log"),
    )


# ---------------------------------------------------------------------------
# Extract — parse log lines into structured records
# ---------------------------------------------------------------------------

# Log line format:  YYYY-MM-DD HH:MM:SS LEVEL message...
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR|INFO|WARN) (.+)$"
)
_USER_ACTION_RE = re.compile(r"^User (\S+) (.+)$")
_API_CALL_RE = re.compile(r"^API (\S+?)(?: took (\d+)ms)?$")


@dataclass
class ErrorRecord:
    """A single parsed error log entry."""

    timestamp: str
    message: str


@dataclass
class ApiRecord:
    """A single parsed API latency log entry."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class UserRecord:
    """A single parsed user-action log entry."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ExtractedData:
    """Container for all data extracted from the log file."""

    errors: List[ErrorRecord] = field(default_factory=list)
    api_calls: List[ApiRecord] = field(default_factory=list)
    user_actions: List[UserRecord] = field(default_factory=list)


def parse_log_line(line: str) -> Optional[object]:
    """Parse a single server log line.

    Recognised formats:

        YYYY-MM-DD HH:MM:SS ERROR <message>
        YYYY-MM-DD HH:MM:SS WARN  <message>
        YYYY-MM-DD HH:MM:SS INFO User <id> logged in
        YYYY-MM-DD HH:MM:SS INFO User <id> logged out
        YYYY-MM-DD HH:MM:SS INFO API <endpoint> took <N>ms
        YYYY-MM-DD HH:MM:SS INFO API <endpoint>

    Args:
        line: A raw log line.

    Returns:
        An ErrorRecord, ApiRecord, or UserRecord if the line matches a known
        format, or None if it does not match the expected log structure.
    """
    match = _LOG_LINE_RE.match(line)
    if not match:
        return None

    timestamp, level, rest = match.groups()

    if level == "ERROR":
        return ErrorRecord(timestamp=timestamp, message=rest)

    if level == "WARN":
        # Parsed for structural recognition but not currently reported.
        return None

    # level == "INFO" — dispatch to sub-parsers
    user_match = _USER_ACTION_RE.match(rest)
    if user_match:
        return UserRecord(
            timestamp=timestamp,
            user_id=user_match.group(1),
            action=user_match.group(2),
        )

    api_match = _API_CALL_RE.match(rest)
    if api_match:
        duration_str = api_match.group(2)
        return ApiRecord(
            timestamp=timestamp,
            endpoint=api_match.group(1),
            duration_ms=int(duration_str) if duration_str else 0,
        )

    return None


def extract(log_file_path: str) -> ExtractedData:
    """Read and parse every line of the log file.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        An ExtractedData container with all recognised log entries.
    """
    data = ExtractedData()

    if not os.path.exists(log_file_path):
        return data

    with open(log_file_path, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            record = parse_log_line(line)
            if isinstance(record, ErrorRecord):
                data.errors.append(record)
            elif isinstance(record, ApiRecord):
                data.api_calls.append(record)
            elif isinstance(record, UserRecord):
                data.user_actions.append(record)

    return data


# ---------------------------------------------------------------------------
# Transform — aggregate raw records into report statistics
# ---------------------------------------------------------------------------


@dataclass
class TransformedData:
    """Aggregated statistics ready for loading."""

    error_summary: Dict[str, int]  # message -> occurrence count
    endpoint_stats: Dict[str, List[int]]  # endpoint -> list of latencies
    active_sessions: int


def _build_error_summary(errors: List[ErrorRecord]) -> Dict[str, int]:
    """Count occurrences of each distinct error message.

    Args:
        errors: Parsed error log entries.

    Returns:
        A dict mapping error message text to occurrence count.
    """
    summary: Dict[str, int] = {}
    for err in errors:
        summary[err.message] = summary.get(err.message, 0) + 1
    return summary


def _build_endpoint_stats(api_calls: List[ApiRecord]) -> Dict[str, List[int]]:
    """Group API latency measurements by endpoint.

    Args:
        api_calls: Parsed API latency entries.

    Returns:
        A dict mapping endpoint paths to lists of measured durations.
    """
    stats: Dict[str, List[int]] = {}
    for call in api_calls:
        stats.setdefault(call.endpoint, []).append(call.duration_ms)
    return stats


def _count_active_sessions(user_actions: List[UserRecord]) -> int:
    """Compute active sessions by replaying login/logout events.

    Args:
        user_actions: Parsed user action entries in chronological order.

    Returns:
        The number of currently active sessions.
    """
    sessions: Dict[str, str] = {}
    for action in user_actions:
        if "logged in" in action.action:
            sessions[action.user_id] = action.timestamp
        elif "logged out" in action.action and action.user_id in sessions:
            del sessions[action.user_id]
    return len(sessions)


def transform(data: ExtractedData) -> TransformedData:
    """Aggregate extracted records into report statistics.

    Args:
        data: Parsed log entries from the extract phase.

    Returns:
        A TransformedData container with computed summaries.
    """
    return TransformedData(
        error_summary=_build_error_summary(data.errors),
        endpoint_stats=_build_endpoint_stats(data.api_calls),
        active_sessions=_count_active_sessions(data.user_actions),
    )


# ---------------------------------------------------------------------------
# Load — persist statistics to database and generate HTML report
# ---------------------------------------------------------------------------


def _init_db(config: Config) -> sqlite3.Connection:
    """Open a connection and ensure the required tables exist.

    Args:
        config: Application configuration.

    Returns:
        An open SQLite connection with created tables.
    """
    conn = sqlite3.connect(config.db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def _insert_errors(
    conn: sqlite3.Connection, error_summary: Dict[str, int]
) -> None:
    """Insert error summary rows using a parameterised query.

    Args:
        conn: Open database connection.
        error_summary: Error message -> occurrence count.
    """
    now = datetime.datetime.now().isoformat()
    for msg, count in error_summary.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def _insert_api_metrics(
    conn: sqlite3.Connection, endpoint_stats: Dict[str, List[int]]
) -> None:
    """Insert API latency summary rows using a parameterised query.

    Args:
        conn: Open database connection.
        endpoint_stats: Endpoint -> list of measured durations.
    """
    now = datetime.datetime.now().isoformat()
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )
    conn.commit()


def _build_error_section(error_summary: Dict[str, int]) -> List[str]:
    """Build the HTML error summary section.

    Args:
        error_summary: Error message -> occurrence count.

    Returns:
        HTML lines for the error summary block.
    """
    lines = ["<h1>Error Summary</h1>", "<ul>"]
    for err_msg, count in sorted(
        error_summary.items(), key=lambda x: -x[1]
    ):
        lines.append(
            f"<li><b>{html.escape(err_msg)}</b>: "
            f"{count} occurrence{'s' if count != 1 else ''}</li>"
        )
    lines.append("</ul>")
    return lines


def _build_api_section(endpoint_stats: Dict[str, List[int]]) -> List[str]:
    """Build the HTML API latency table section.

    Args:
        endpoint_stats: Endpoint -> list of measured durations.

    Returns:
        HTML lines for the API latency table block.
    """
    lines = [
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for ep, times in sorted(endpoint_stats.items()):
        avg = sum(times) / len(times)
        lines.append(
            f"<tr><td>{html.escape(ep)}</td>"
            f"<td>{round(avg, 1)}</td></tr>"
        )
    lines.append("</table>")
    return lines


def _build_session_section(active_sessions: int) -> List[str]:
    """Build the HTML active session count section.

    Args:
        active_sessions: Number of currently active sessions.

    Returns:
        HTML lines for the session count block.
    """
    return [
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user{'s' if active_sessions != 1 else ''} "
        f"currently active</p>",
    ]


def _generate_report(data: TransformedData) -> str:
    """Build the complete HTML report document.

    Args:
        data: Transformed statistics.

    Returns:
        Complete HTML document as a string.
    """
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
    ]
    lines.extend(_build_error_section(data.error_summary))
    lines.extend(_build_api_section(data.endpoint_stats))
    lines.extend(_build_session_section(data.active_sessions))
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def load(
    config: Config,
    data: TransformedData,
) -> None:
    """Persist statistics to database and write HTML report.

    Args:
        config: Application configuration.
        data: Transformed statistics.
    """
    conn = _init_db(config)
    try:
        _insert_errors(conn, data.error_summary)
        _insert_api_metrics(conn, data.endpoint_stats)
    finally:
        conn.close()

    report_html = _generate_report(data)
    with open("report.html", "w") as f:
        f.write(report_html)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full Extract-Transform-Load pipeline."""
    config = load_config()
    raw = extract(config.log_file_path)
    aggregated = transform(raw)
    load(config, aggregated)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _ensure_sample_log(config: Config) -> None:
    """Write a sample log file if none exists.

    Matches the log format consumed by the original pipeline so the
    refactored version produces identical output from identical input.

    Args:
        config: Application configuration.
    """
    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(config.log_file_path, "w") as f:
        for line in sample_lines:
            f.write(line + "\n")


if __name__ == "__main__":
    cfg = load_config()
    if not os.path.exists(cfg.log_file_path):
        _ensure_sample_log(cfg)
    run_pipeline()
