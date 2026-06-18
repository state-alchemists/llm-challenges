"""Log processing pipeline: parse, transform, and report on server log data.

Reads server logs, extracts ERROR/WARN/INFO entries (user sessions and API
latency), computes aggregates, stores results in SQLite, and writes an HTML
summary report.
"""

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Tuple


# --- Regex patterns for log line parsing ---

_RE_ERROR = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$"
)
_RE_WARN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.+)$"
)
_RE_USER = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\d+) (.+)$"
)
_RE_API = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"
)


# --- Data containers ---


@dataclass
class LogEvent:
    """A single parsed log entry — error, warning, or user action."""

    timestamp: str
    kind: str
    message: str
    user_id: str = ""


@dataclass(frozen=True)
class ApiCall:
    """Latency measurement for one API call."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class Config:
    """Runtime settings sourced from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_password: str


# --- Configuration ---


def load_config() -> Config:
    """Read configuration from environment variables with sensible defaults.

    Returns:
        Config populated from env vars (or fallback defaults).
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_password=os.getenv("DB_PASS", "password123"),
    )


# --- Extract phase ---


def extract_log_events(
    log_path: str,
) -> Tuple[List[LogEvent], List[ApiCall], Dict[str, str]]:
    """Parse a server log file into structured events, API calls, and sessions.

    Args:
        log_path: Path to the server log file.

    Returns:
        Tuple of (events list, API calls list, active sessions dict).
    """
    events: List[LogEvent] = []
    api_calls: List[ApiCall] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_path):
        return events, api_calls, sessions

    with open(log_path, "r") as f:
        for line in f:
            line = line.rstrip("\n")

            m = _RE_ERROR.match(line)
            if m:
                events.append(
                    LogEvent(timestamp=m.group(1), kind="ERR", message=m.group(2))
                )
                continue

            m = _RE_WARN.match(line)
            if m:
                events.append(
                    LogEvent(timestamp=m.group(1), kind="WARN", message=m.group(2))
                )
                continue

            m = _RE_API.match(line)
            if m:
                api_calls.append(
                    ApiCall(
                        timestamp=m.group(1),
                        endpoint=m.group(2),
                        duration_ms=int(m.group(3)),
                    )
                )
                continue

            m = _RE_USER.match(line)
            if m:
                ts, uid, action = m.group(1), m.group(2), m.group(3)
                events.append(
                    LogEvent(
                        timestamp=ts, kind="USR", message=action, user_id=uid
                    )
                )
                if "logged in" in action:
                    sessions[uid] = ts
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]

    return events, api_calls, sessions


# --- Transform phase ---


def transform_error_counts(events: List[LogEvent]) -> Dict[str, int]:
    """Aggregate error messages into count-per-unique-message.

    Args:
        events: Parsed log events.

    Returns:
        Mapping of error message text to occurrence count.
    """
    counts: Dict[str, int] = {}
    for ev in events:
        if ev.kind == "ERR":
            counts[ev.message] = counts.get(ev.message, 0) + 1
    return counts


def transform_api_stats(api_calls: List[ApiCall]) -> Dict[str, float]:
    """Compute average latency in milliseconds per API endpoint.

    Args:
        api_calls: Parsed API call measurements.

    Returns:
        Mapping of endpoint path to average latency in milliseconds.
    """
    totals: Dict[str, List[int]] = {}
    for call in api_calls:
        totals.setdefault(call.endpoint, []).append(call.duration_ms)
    return {
        ep: sum(times) / len(times) for ep, times in totals.items()
    }


# --- Load phase ---


def load_metrics_to_db(
    db_path: str, errors: Dict[str, int], api_stats: Dict[str, float]
) -> None:
    """Insert aggregated error counts and API latencies into SQLite.

    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        errors: Mapping of error message to occurrence count.
        api_stats: Mapping of endpoint to average latency in ms.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now()
    for msg, count in errors.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    for ep, avg in api_stats.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    errors: Dict[str, int],
    api_stats: Dict[str, float],
    active_session_count: int,
) -> str:
    """Build a standalone HTML report with error summary, latency table, and session count.

    Args:
        errors: Mapping of error message to occurrence count.
        api_stats: Mapping of endpoint to average latency in ms.
        active_session_count: Number of currently active user sessions.

    Returns:
        Complete HTML document as a string.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in errors.items():
        safe_msg = html.escape(msg)
        lines.append(f"<li><b>{safe_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in sorted(api_stats.items()):
        lines.append(
            f"<tr><td>{html.escape(ep)}</td><td>{round(avg, 1)}</td></tr>"
        )
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


# --- Orchestration ---


def _create_sample_log(log_path: str) -> None:
    """Write a sample server log for demo / testing when none exists.

    Args:
        log_path: Path where the sample log should be written.
    """
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    with open(log_path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> None:
    """Run the full pipeline: extract, transform, load, and generate report."""
    cfg = load_config()

    if not os.path.exists(cfg.log_file):
        _create_sample_log(cfg.log_file)

    events, api_calls, sessions = extract_log_events(cfg.log_file)

    error_counts = transform_error_counts(events)
    api_stats = transform_api_stats(api_calls)

    load_metrics_to_db(cfg.db_path, error_counts, api_stats)

    html_output = generate_html_report(error_counts, api_stats, len(sessions))
    with open("report.html", "w") as f:
        f.write(html_output)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
