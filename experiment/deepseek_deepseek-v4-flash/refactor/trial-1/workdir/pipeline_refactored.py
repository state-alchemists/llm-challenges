"""
Pipeline: server log extractor, transformer, and reporter.

Reads a server log file, parses entries for errors, user sessions (login/logout),
and API call latencies, then persists aggregates to SQLite and produces report.html.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load configuration from environment variables with sensible defaults.

    Returns
    -------
    dict[str, Any]
        Keys: ``db_path``, ``log_file``, ``db_host``, ``db_port``,
        ``db_user``, ``db_pass``.
    """
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": int(os.environ.get("DB_PORT", "5432")),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def read_log_lines(path: str) -> list[str]:
    """Read all non-empty lines from *path*.

    Parameters
    ----------
    path : str
        Path to the log file.

    Returns
    -------
    list[str]
        Stripped, non-empty lines.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]


_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.+)$"
)
"""Regex for a log line: timestamp, level, message body."""

_USER_RE = re.compile(r"User (\S+) (.+)")
"""Regex for an INFO User event: extracts user id and action."""

_API_RE = re.compile(r"API (\S+) took (\d+)ms")
"""Regex for an INFO API call: extracts endpoint and duration in ms."""


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a single log line into a structured dict, or return ``None``.

    The returned dict always contains keys ``timestamp``, ``level``, and
    ``raw``.  Additional keys depend on the entry type:

    - ``ERROR`` / ``WARN`` → ``message``
    - ``INFO`` + ``User``  → ``user_id``, ``action``
    - ``INFO`` + ``API``   → ``endpoint``, ``duration_ms``

    Parameters
    ----------
    line : str
        A single log line.

    Returns
    -------
    dict[str, Any] | None
        Parsed entry, or ``None`` if the line does not match the expected
        format.
    """
    m = _LOG_LINE_RE.match(line)
    if not m:
        return None

    ts, level, body = m.group(1), m.group(2), m.group(3)

    if level == "ERROR":
        return {"timestamp": ts, "level": "ERROR", "message": body, "raw": line}

    if level == "WARN":
        return {"timestamp": ts, "level": "WARN", "message": body, "raw": line}

    # --- INFO ---------------------------------------------------------------
    # User event?
    user_m = _USER_RE.match(body)
    if user_m:
        uid = user_m.group(1)
        action = user_m.group(2)
        return {
            "timestamp": ts,
            "level": "INFO",
            "user_id": uid,
            "action": action,
            "raw": line,
        }

    # API call?
    api_m = _API_RE.search(body)
    if api_m:
        return {
            "timestamp": ts,
            "level": "INFO",
            "endpoint": api_m.group(1),
            "duration_ms": int(api_m.group(2)),
            "raw": line,
        }

    # Unrecognised INFO – still record it but with no extra payload.
    return {"timestamp": ts, "level": "INFO", "message": body, "raw": line}


def parse_log_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Parse multiple log lines, skipping any that don't match.

    Parameters
    ----------
    lines : list[str]
        Raw log lines.

    Returns
    -------
    list[dict[str, Any]]
        Parsed entries in input order.
    """
    return [e for line in lines if (e := parse_log_line(line)) is not None]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def track_sessions(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Replay user login/logout events to determine active sessions.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Parsed log entries.

    Returns
    -------
    dict[str, str]
        Mapping of active user id → login timestamp.
    """
    sessions: dict[str, str] = {}
    for e in entries:
        if e.get("level") == "INFO" and "user_id" in e:
            uid = e["user_id"]
            action = e["action"]
            if "logged in" in action:
                sessions[uid] = e["timestamp"]
            elif "logged out" in action and uid in sessions:
                del sessions[uid]
    return sessions


def aggregate_errors(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each unique error message.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Parsed log entries.

    Returns
    -------
    dict[str, int]
        Error message → occurrence count.
    """
    counts: dict[str, int] = {}
    for e in entries:
        if e.get("level") == "ERROR":
            msg = e["message"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def aggregate_api_latency(
    entries: list[dict[str, Any]],
) -> dict[str, list[int]]:
    """Collect API call durations per endpoint.

    Parameters
    ----------
    entries : list[dict[str, Any]]
        Parsed log entries.

    Returns
    -------
    dict[str, list[int]]
        Endpoint → list of duration (ms) values.
    """
    stats: dict[str, list[int]] = defaultdict(list)
    for e in entries:
        if "duration_ms" in e:
            stats[e["endpoint"]].append(e["duration_ms"])
    return dict(stats)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def setup_database(conn: sqlite3.Connection) -> None:
    """Create the metrics tables if they do not exist.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def save_error_summary(
    conn: sqlite3.Connection, error_counts: dict[str, int]
) -> None:
    """Insert error summary rows using parameterised queries.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    error_counts : dict[str, int]
        Error message → occurrence count.
    """
    now = datetime.datetime.now().isoformat()
    for msg, count in error_counts.items():
        conn.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def save_api_metrics(
    conn: sqlite3.Connection, endpoint_stats: dict[str, list[int]]
) -> None:
    """Insert API latency rows using parameterised queries.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    endpoint_stats : dict[str, list[int]]
        Endpoint → list of duration (ms) values.
    """
    now = datetime.datetime.now().isoformat()
    for endpoint, durations in endpoint_stats.items():
        avg_ms = sum(durations) / len(durations)
        conn.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )
    conn.commit()


def generate_report_html(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, list[int]],
    session_count: int,
) -> str:
    """Produce a report.html string with error summary, API latency table,
    and active-session count.

    Parameters
    ----------
    error_counts : dict[str, int]
        Error message → occurrence count.
    endpoint_stats : dict[str, list[int]]
        Endpoint → list of duration (ms) values.
    session_count : int
        Number of currently active user sessions.

    Returns
    -------
    str
        Complete HTML document.
    """
    parts: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in error_counts.items():
        parts.append(
            f"<li><b>{err_msg}</b>: {count} occurrences</li>"
        )
    parts.append("</ul>")

    parts.append("<h2>API Latency</h2>")
    parts.append("<table border='1'>")
    parts.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, durations in endpoint_stats.items():
        avg = sum(durations) / len(durations)
        parts.append(
            f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Active Sessions</h2>")
    parts.append(f"<p>{session_count} user(s) currently active</p>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(cfg: dict[str, Any]) -> None:
    """Execute the full Extract → Transform → Load pipeline.

    Parameters
    ----------
    cfg : dict[str, Any]
        Configuration dictionary from :func:`load_config`.
    """
    # Extract
    raw_lines = read_log_lines(cfg["log_file"])
    entries = parse_log_lines(raw_lines)

    # Transform
    active_sessions = track_sessions(entries)
    error_counts = aggregate_errors(entries)
    api_stats = aggregate_api_latency(entries)

    # Load (database)
    conn = sqlite3.connect(cfg["db_path"])
    try:
        setup_database(conn)
        save_error_summary(conn, error_counts)
        save_api_metrics(conn, api_stats)
    finally:
        conn.close()

    # Load (report)
    html = generate_report_html(error_counts, api_stats, len(active_sessions))
    with open("report.html", "w") as f:
        f.write(html)

    print(f"Pipeline complete at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    config = load_config()

    # Generate a minimal sample log if one does not exist yet.
    if not os.path.exists(config["log_file"]):
        with open(config["log_file"], "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline(config)
