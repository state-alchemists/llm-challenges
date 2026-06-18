"""
Server log processing pipeline.

Extracts metrics from server logs, stores aggregates in a SQLite database,
and generates an HTML report.
"""

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict

# ---------------------------------------------------------------------------
# Configuration (all loaded from environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
REPORT_FILE: str = os.environ.get("REPORT_FILE", "report.html")
_DB_HOST: str = os.environ.get("DB_HOST", "localhost")
_DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
_DB_USER: str = os.environ.get("DB_USER", "")
_DB_PASS: str = os.environ.get("DB_PASS", "")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class ErrorRecord(TypedDict):
    dt: str
    t: str
    m: str


class UserRecord(TypedDict):
    dt: str
    t: str
    u: str
    a: str


class ApiCallRecord(TypedDict):
    d: str
    endpoint: str
    ms: int


class WarnRecord(TypedDict):
    dt: str
    t: str
    m: str


ParsedLog = list[ErrorRecord | UserRecord | ApiCallRecord | WarnRecord]
SessionMap = dict[str, str]  # uid -> login timestamp
EndpointStats = dict[str, list[int]]  # endpoint -> list of latencies in ms


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_LOG_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<rest>.+)$"
)

# NOTE: these patterns match against `rest` (the line with the level word
# already stripped), so they do NOT re-match the level prefix.
_RE_ERROR = re.compile(r"(?P<msg>.+)")

_RE_USER_ACTION = re.compile(
    r"User (?P<uid>\S+) (?P<action>logged in|logged out)"
)

_RE_API_LATENCY = re.compile(
    r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms"
)

_RE_WARN = re.compile(r"(?P<msg>.+)")


# ---------------------------------------------------------------------------
# EXTRACT: Parse log file
# ---------------------------------------------------------------------------


def extract_log_entries(log_path: str) -> tuple[ParsedLog, SessionMap, EndpointStats]:
    """
    Parse ``log_path`` and return structured records plus live session state.

    Returns
    -------
    records : ParsedLog
        All parsed log lines as typed dicts.
    sessions : SessionMap
        Map of user IDs to login timestamps for users still logged in.
    api_calls : EndpointStats
        Map of endpoint paths to latency samples (ms).
    """
    records: ParsedLog = []
    sessions: SessionMap = {}
    api_calls: EndpointStats = {}

    if not os.path.exists(log_path):
        return records, sessions, api_calls

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.strip()
            m = _RE_LOG_LINE.match(line)
            if not m:
                continue

            timestamp = m.group("timestamp")
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                err_m = _RE_ERROR.match(rest)
                if err_m:
                    records.append(ErrorRecord(dt=timestamp, t="ERR", m=err_m.group("msg")))

            elif level == "INFO":
                user_m = _RE_USER_ACTION.match(rest)
                if user_m:
                    uid = user_m.group("uid")
                    action = user_m.group("action")
                    if action == "logged in":
                        sessions[uid] = timestamp
                    elif action == "logged out" and uid in sessions:
                        sessions.pop(uid)
                    records.append(UserRecord(dt=timestamp, t="USR", u=uid, a=action))
                    continue

                api_m = _RE_API_LATENCY.match(rest)
                if api_m:
                    endpoint = api_m.group("endpoint")
                    ms = int(api_m.group("ms"))
                    api_calls.setdefault(endpoint, []).append(ms)
                    records.append(ApiCallRecord(d=timestamp, endpoint=endpoint, ms=ms))

            elif level == "WARN":
                warn_m = _RE_WARN.match(rest)
                if warn_m:
                    records.append(WarnRecord(dt=timestamp, t="WARN", m=warn_m.group("msg")))

    return records, sessions, api_calls


# ---------------------------------------------------------------------------
# TRANSFORM: Aggregate data
# ---------------------------------------------------------------------------


def aggregate_errors(records: ParsedLog) -> dict[str, int]:
    """
    Count occurrences of each unique error message.

    Returns
    -------
    dict[str, int]
        Error message -> total count.
    """
    counts: dict[str, int] = {}
    for rec in records:
        if rec.get("t") == "ERR":
            msg: str = rec["m"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def compute_endpoint_stats(api_calls: EndpointStats) -> dict[str, float]:
    """
    Compute average latency per endpoint.

    Returns
    -------
    dict[str, float]
        Endpoint path -> average latency in ms.
    """
    return {ep: sum(times) / len(times) for ep, times in api_calls.items()}


# ---------------------------------------------------------------------------
# LOAD: Write to DB and produce HTML report
# ---------------------------------------------------------------------------


def load_metrics(
    db_path: str,
    error_counts: dict[str, int],
    endpoint_stats: dict[str, float],
    db_host: str,
    db_port: int,
    db_user: str,
    db_pass: str,
) -> None:
    """
    Persist error counts and endpoint latency averages to the SQLite database
    using parameterized queries.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    error_counts : dict[str, int]
        Error message -> count.
    endpoint_stats : dict[str, float]
        Endpoint -> average latency (ms).
    db_host, db_port, db_user, db_pass :
        Connection metadata (printed but not used by sqlite3).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user} ...")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        # Parameterized query — no string formatting, no injection risk.
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg_ms in endpoint_stats.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: dict[str, int],
    endpoint_stats: dict[str, float],
    active_session_count: int,
    report_path: str,
) -> None:
    """
    Render the HTML report covering error summary, API latency table,
    and active session count.

    Parameters
    ----------
    error_counts : dict[str, int]
        Error message -> count.
    endpoint_stats : dict[str, float]
        Endpoint -> average latency (ms).
    active_session_count : int
        Number of currently active (logged-in) sessions.
    report_path : str
        Destination file path for the HTML output.
    """
    now = datetime.datetime.now().isoformat()

    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        f"<p><i>Generated at {now}</i></p>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    if error_counts:
        for msg, count in error_counts.items():
            lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    else:
        lines.append("<li>No errors recorded.</li>")

    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")

    if endpoint_stats:
        for ep, avg in endpoint_stats.items():
            lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    else:
        lines.append("<tr><td colspan='2'>No API calls recorded.</td></tr>")

    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Execute the full ETL pipeline: extract, transform, load, report."""
    # EXTRACT
    records, sessions, api_calls = extract_log_entries(LOG_FILE)

    # TRANSFORM
    error_counts = aggregate_errors(records)
    endpoint_stats = compute_endpoint_stats(api_calls)

    # LOAD — database
    load_metrics(
        db_path=DB_PATH,
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        db_host=_DB_HOST,
        db_port=_DB_PORT,
        db_user=_DB_USER,
        db_pass=_DB_PASS,
    )

    # LOAD — HTML report
    generate_report(
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        active_session_count=len(sessions),
        report_path=REPORT_FILE,
    )

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a sample log when none exists so the script is self-contained.
    if not os.path.exists(LOG_FILE):
        sample_lines = [
            "2024-01-01 12:00:00 INFO User 42 logged in",
            "2024-01-01 12:05:00 ERROR Database timeout",
            "2024-01-01 12:05:05 ERROR Database timeout",
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
            "2024-01-01 12:09:00 WARN Memory usage at 87%",
            "2024-01-01 12:10:00 INFO User 42 logged out",
        ]
        Path(LOG_FILE).write_text("\n".join(sample_lines) + "\n")

    run_pipeline()
