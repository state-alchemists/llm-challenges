"""
Log processing pipeline: Extract → Transform → Load → Report.

Produces a self-contained HTML report from a structured server log.
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
import sys
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Configuration (all sourced from environment variables)
# ---------------------------------------------------------------------------

class Config(NamedTuple):
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read pipeline configuration from environment variables."""
    missing: list[str] = []
    env = {
        "DB_PATH": os.environ.get("DB_PATH", ""),
        "LOG_FILE": os.environ.get("LOG_FILE", ""),
        "DB_HOST": os.environ.get("DB_HOST", ""),
        "DB_PORT": os.environ.get("DB_PORT", ""),
        "DB_USER": os.environ.get("DB_USER", ""),
        "DB_PASS": os.environ.get("DB_PASS", ""),
    }
    for key, val in env.items():
        if not val:
            missing.append(key)

    if missing:
        print(f"Error: missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    return Config(
        db_path=env["DB_PATH"],
        log_file=env["LOG_FILE"],
        db_host=env["DB_HOST"],
        db_port=int(env["DB_PORT"]),
        db_user=env["DB_USER"],
        db_pass=env["DB_PASS"],
    )


# ---------------------------------------------------------------------------
# Regex patterns (compiled once, reused)
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"ERROR (?P<message>.+)$"
)
_RE_WARN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"WARN (?P<message>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO User (?P<uid>\S+) (?P<action>.+)$"
)
_RE_API = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"INFO API (?P<endpoint>\S+) (?P<timing>took \d+ms)$"
)


# ---------------------------------------------------------------------------
# Log record types
# ---------------------------------------------------------------------------

class ErrorRecord(NamedTuple):
    timestamp: str
    message: str


class WarnRecord(NamedTuple):
    timestamp: str
    message: str


class UserRecord(NamedTuple):
    timestamp: str
    uid: str
    action: str


class ApiRecord(NamedTuple):
    timestamp: str
    endpoint: str
    latency_ms: int


# ---------------------------------------------------------------------------
# EXTRACT — read and parse the log file
# ---------------------------------------------------------------------------

def extract_log_records(log_path: str) -> tuple[
    list[ErrorRecord], list[WarnRecord], list[UserRecord], list[ApiRecord]
]:
    """
    Parse a server log file, returning four lists of typed records.

    Lines are matched against INFO/WARN/ERROR patterns using regex.
    Unrecognised lines are silently skipped.
    """
    errors: list[ErrorRecord] = []
    warns: list[WarnRecord] = []
    users: list[UserRecord] = []
    apis: list[ApiRecord] = []

    if not os.path.exists(log_path):
        print(f"Warning: log file '{log_path}' not found; starting with empty data.")
        return errors, warns, users, apis

    with open(log_path, "r") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if m := _RE_ERROR.match(line):
                errors.append(ErrorRecord(m["timestamp"], m["message"]))
            elif m := _RE_WARN.match(line):
                warns.append(WarnRecord(m["timestamp"], m["message"]))
            elif m := _RE_USER.match(line):
                users.append(UserRecord(m["timestamp"], m["uid"], m["action"]))
            elif m := _RE_API.match(line):
                latency = int(re.search(r"\d+", m["timing"]).group())  # type: ignore[union-attr]
                apis.append(ApiRecord(m["timestamp"], m["endpoint"], latency))

    return errors, warns, users, apis


# ---------------------------------------------------------------------------
# TRANSFORM — aggregate parsed records into report-ready summaries
# ---------------------------------------------------------------------------

def aggregate_errors(errors: list[ErrorRecord]) -> dict[str, int]:
    """
    Count occurrences of each distinct error message.

    Returns a dict mapping message -> count.
    """
    counts: dict[str, int] = {}
    for rec in errors:
        counts[rec.message] = counts.get(rec.message, 0) + 1
    return counts


def aggregate_api_latency(apis: list[ApiRecord]) -> dict[str, list[int]]:
    """
    Group API records by endpoint, preserving individual latency values.

    Returns a dict mapping endpoint -> list of latency_ms values.
    """
    by_endpoint: dict[str, list[int]] = {}
    for rec in apis:
        by_endpoint.setdefault(rec.endpoint, []).append(rec.latency_ms)
    return by_endpoint


def compute_active_sessions(users: list[UserRecord]) -> int:
    """
    Track session start/end events and return the number of currently
    active (logged-in, not-yet-logged-out) sessions.

    A "User <uid> logged in" event opens a session; "logged out" closes it.
    """
    active: set[str] = set()
    for rec in users:
        if "logged in" in rec.action:
            active.add(rec.uid)
        elif "logged out" in rec.action:
            active.discard(rec.uid)
    return len(active)


# ---------------------------------------------------------------------------
# LOAD — write summaries into SQLite using parameterised queries
# ---------------------------------------------------------------------------

def load_into_db(
    config: Config,
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
) -> None:
    """
    Connect to the database, create (or reuse) the two metric tables,
    and insert the aggregated data using parameterised queries.

    Credentials are read from *config* but are printed only as a
    redacted summary to avoid accidental exposure in logs.
    """
    print(
        f"Connecting to {config.db_host}:{config.db_port} as "
        f"{config.db_user} (password=****) ..."
    )

    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    # Parameterised INSERT — safe against injection
    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, latencies in api_latency.items():
        avg = sum(latencies) / len(latencies)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# REPORT — generate the self-contained HTML output
# ---------------------------------------------------------------------------

def build_html_report(
    error_counts: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: int,
) -> str:
    """
    Render the three-section HTML report.

    Sections: Error Summary, API Latency table, Active Session count.
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, latencies in api_latency.items():
        avg = sum(latencies) / len(latencies)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def write_report(html: str, output_path: str = "report.html") -> None:
    """Write the HTML string to *output_path*, overwriting any existing file."""
    with open(output_path, "w") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Main pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """Load config → Extract → Transform → Load → Report."""
    config = load_config()

    errors, warns, users, apis = extract_log_records(config.log_file)

    error_counts = aggregate_errors(errors)
    api_latency = aggregate_api_latency(apis)
    active_sessions = compute_active_sessions(users)

    load_into_db(config, error_counts, api_latency)

    report = build_html_report(error_counts, api_latency, active_sessions)
    write_report(report)

    print(f"Job finished at {datetime.datetime.now().isoformat()}")


# ---------------------------------------------------------------------------
# Bootstrap: create a sample log when run directly with no input
# ---------------------------------------------------------------------------

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


if __name__ == "__main__":
    # When running standalone, populate a sample log so the script is
    # immediately exercisable without external fixtures.
    log_path = os.environ.get("LOG_FILE", "server.log")
    if not os.path.exists(log_path):
        with open(log_path, "w") as fh:
            fh.write(_SAMPLE_LOG)

    # Apply default values for non-interactive / CI use when env vars are
    # not yet set (ids/passwords are placeholder values for the sample log).
    for key, val in {
        "DB_PATH": "metrics.db",
        "LOG_FILE": "server.log",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "admin",
        "DB_PASS": "password123",
    }.items():
        os.environ.setdefault(key, val)

    run_pipeline()
