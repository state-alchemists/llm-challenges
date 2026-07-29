"""
Log processing pipeline that extracts server logs, transforms metrics,
and loads summaries into a SQLite database with HTML reporting.
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Sequence, TypedDict, cast


# --- Config (from environment) ---

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")


# --- Types ---

class ErrorRecord(TypedDict):
    dt: str
    t: str
    m: str


class UserRecord(TypedDict):
    dt: str
    t: str
    u: str
    a: str


class ApiRecord(TypedDict):
    d: str
    endpoint: str
    ms: int


class WarnRecord(TypedDict):
    dt: str
    t: str
    m: str


LogRecord = ErrorRecord | UserRecord | ApiRecord | WarnRecord


# --- Regex patterns ---

_RE_LOG_LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN|DEBUG)\s+"
    r"(?P<rest>.*)"
)

_RE_ERROR = re.compile(r"(?P<msg>.+)")

_RE_USER_ACTION = re.compile(
    r"^User\s+(?P<uid>\S+)\s+(?P<action>logged\s+in|logged\s+out)"
)

_RE_API_CALL = re.compile(
    r"^API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms"
)

_RE_WARN = re.compile(r"(?P<msg>.+)")


# --- Extract ---

def extract_log_records(log_path: str) -> tuple[list[LogRecord], dict[str, str]]:
    """
    Parse a log file and return structured records plus active sessions.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple of (list of log records, dict of active user sessions keyed by uid).
    """
    records: list[LogRecord] = []
    sessions: dict[str, str] = {}

    if not os.path.exists(log_path):
        return records, sessions

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.strip()
            m = _RE_LOG_LINE.match(line)
            if not m:
                continue

            dt = f"{m.group('date')} {m.group('time')}"
            level = m.group("level")
            rest = m.group("rest")

            if level == "ERROR":
                em = _RE_ERROR.match(rest)
                msg = em.group("msg") if em else rest
                records.append(ErrorRecord(dt=dt, t="ERR", m=msg))  # type: ignore[arg-type]

            elif level == "INFO" and rest.startswith("User"):
                um = _RE_USER_ACTION.match(rest)
                if um:
                    uid = um.group("uid")
                    action = um.group("action")
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        del sessions[uid]
                    records.append(UserRecord(dt=dt, t="USR", u=uid, a=action))  # type: ignore[arg-type]

            elif level == "INFO" and rest.startswith("API"):
                am = _RE_API_CALL.match(rest)
                if am:
                    records.append(ApiRecord(  # type: ignore[arg-type]
                        d=dt,
                        endpoint=am.group("endpoint"),
                        ms=int(am.group("ms")),
                    ))

            elif level == "WARN":
                wm = _RE_WARN.match(rest)
                msg = wm.group("msg") if wm else rest
                records.append(WarnRecord(dt=dt, t="WARN", m=msg))  # type: ignore[arg-type]

    return records, sessions


# --- Transform ---

def transform_error_counts(errors: Sequence[ErrorRecord]) -> dict[str, int]:
    """
    Aggregate error messages and their occurrence counts.

    Args:
        errors: Parsed ERROR-level log records.

    Returns:
        Dict mapping error message to occurrence count.
    """
    counts: dict[str, int] = {}
    for rec in errors:
        counts[rec["m"]] = counts.get(rec["m"], 0) + 1
    return counts


def transform_api_latency(api_calls: list[ApiRecord]) -> dict[str, list[int]]:
    """
    Collect per-endpoint latency samples for averaging.

    Args:
        api_calls: Parsed API call log records.

    Returns:
        Dict mapping endpoint to list of latency values (ms).
    """
    endpoint_times: dict[str, list[int]] = {}
    for rec in api_calls:
        endpoint_times.setdefault(rec["endpoint"], []).append(rec["ms"])
    return endpoint_times


# --- Load ---

def load_to_db(
    db_path: str,
    errors: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """
    Write error summaries and API latency aggregates to SQLite.

    Args:
        db_path: Path to the SQLite database file.
        errors: Error message -> count mapping.
        api_latency: Endpoint -> list of latency values (ms) mapping.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in errors.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    output_path: str,
    errors: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
) -> None:
    """
    Render the pipeline summary as an HTML report.

    Args:
        output_path: Destination file path for the HTML report.
        errors: Error message -> count mapping.
        api_latency: Endpoint -> list of latency values (ms) mapping.
        active_sessions: Number of currently active user sessions.
    """
    rows_err = "".join(
        f"<li><b>{msg}</b>: {count} occurrences</li>\n"
        for msg, count in errors.items()
    )
    if not rows_err:
        rows_err = "<li>No errors recorded</li>\n"

    rows_api = "".join(
        f"<tr><td>{ep}</td><td>{round(sum(times)/len(times), 1)}</td></tr>\n"
        for ep, times in api_latency.items()
    )
    if not rows_api:
        rows_api = "<tr><td colspan='2'>No API calls recorded</td></tr>\n"

    html = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        "<h1>Error Summary</h1>\n"
        f"<ul>\n{rows_err}</ul>\n"
        "<h2>API Latency</h2>\n"
        "<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        f"{rows_api}"
        "</table>\n"
        "<h2>Active Sessions</h2>\n"
        f"<p>{active_sessions} user(s) currently active</p>\n"
        "</body>\n</html>\n"
    )

    with open(output_path, "w") as fh:
        fh.write(html)


# --- Pipeline ---

def run_pipeline() -> None:
    """
    Execute the full ETL pipeline: extract, transform, load, and report.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    records, sessions = extract_log_records(LOG_FILE)
    print(f"Extracted {len(records)} records from {LOG_FILE}")

    error_records = cast("list[ErrorRecord]", [r for r in records if r.get("t") == "ERR"])
    api_records = cast("list[ApiRecord]", [r for r in records if "endpoint" in r])

    errors = transform_error_counts(error_records)
    api_latency = transform_api_latency(api_records)

    load_to_db(DB_PATH, errors, api_latency)
    print(f"Wrote metrics to {DB_PATH}")

    generate_html_report("report.html", errors, api_latency, len(sessions))
    print(f"Report written to report.html ({len(sessions)} active sessions)")

    print(f"Job finished at {datetime.datetime.now()}")


# --- Bootstrap ---

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run_pipeline()
