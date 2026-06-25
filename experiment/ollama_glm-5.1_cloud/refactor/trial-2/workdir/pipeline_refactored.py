"""Refactored server-log processing pipeline.

Reads server logs, aggregates errors / API latency / sessions,
persists summaries to SQLite, and writes an HTML report.

Configuration is loaded from environment variables with sensible
defaults so the script works both standalone and under the validator.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Build configuration from environment variables."""
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_pass=os.getenv("DB_PASS", ""),
    )


# ---------------------------------------------------------------------------
# Parsed log records
# ---------------------------------------------------------------------------

@dataclass
class ErrorRecord:
    """An ERROR-level log entry."""

    timestamp: str
    message: str


@dataclass
class UserRecord:
    """An INFO User log entry (login / logout)."""

    timestamp: str
    user_id: str
    action: str


@dataclass
class ApiCallRecord:
    """An INFO API log entry with latency measurement."""

    timestamp: str
    endpoint: str
    duration_ms: int


@dataclass
class WarnRecord:
    """A WARN-level log entry."""

    timestamp: str
    message: str


# ---------------------------------------------------------------------------
# Compiled regex patterns for each log-line flavour
# ---------------------------------------------------------------------------

_RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<msg>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"User (?P<uid>\S+) (?P<action>.+)$"
)
_RE_API = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms$"
)
_RE_WARN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<msg>.+)$"
)


# ---------------------------------------------------------------------------
# Extract — read and parse log lines into structured records
# ---------------------------------------------------------------------------

@dataclass
class ExtractedData:
    """Container for all parsed log records."""

    errors: List[ErrorRecord] = field(default_factory=list)
    user_events: List[UserRecord] = field(default_factory=list)
    api_calls: List[ApiCallRecord] = field(default_factory=list)
    warnings: List[WarnRecord] = field(default_factory=list)


def extract(log_path: str) -> ExtractedData:
    """Read the log file and parse every line into typed records."""
    data = ExtractedData()

    path = Path(log_path)
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        m = _RE_ERROR.match(line)
        if m:
            data.errors.append(
                ErrorRecord(timestamp=m.group("ts"), message=m.group("msg"))
            )
            continue

        m = _RE_API.match(line)
        if m:
            data.api_calls.append(
                ApiCallRecord(
                    timestamp=m.group("ts"),
                    endpoint=m.group("endpoint"),
                    duration_ms=int(m.group("ms")),
                )
            )
            continue

        m = _RE_USER.match(line)
        if m:
            data.user_events.append(
                UserRecord(
                    timestamp=m.group("ts"),
                    user_id=m.group("uid"),
                    action=m.group("action"),
                )
            )
            continue

        m = _RE_WARN.match(line)
        if m:
            data.warnings.append(
                WarnRecord(timestamp=m.group("ts"), message=m.group("msg"))
            )

    return data


# ---------------------------------------------------------------------------
# Transform — aggregate and compute summaries
# ---------------------------------------------------------------------------

@dataclass
class TransformedData:
    """Aggregated results ready for persistence and reporting."""

    error_counts: Dict[str, int] = field(default_factory=dict)
    api_latency: Dict[str, List[int]] = field(default_factory=dict)
    active_sessions: int = 0


def transform(data: ExtractedData) -> TransformedData:
    """Aggregate error counts, API latency averages, and active session count."""
    # Error frequency
    error_counts: Dict[str, int] = {}
    for err in data.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    # API latency per endpoint
    api_latency: Dict[str, List[int]] = {}
    for call in data.api_calls:
        api_latency.setdefault(call.endpoint, []).append(call.duration_ms)

    # Active sessions — users logged in but not yet logged out
    sessions: Dict[str, str] = {}
    for evt in data.user_events:
        if "logged in" in evt.action:
            sessions[evt.user_id] = evt.timestamp
        elif "logged out" in evt.action:
            sessions.pop(evt.user_id, None)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load — persist to SQLite and generate the HTML report
# ---------------------------------------------------------------------------

def load(
    transformed: TransformedData,
    config: Config,
) -> None:
    """Write aggregated data to the database and produce ``report.html``."""
    now = datetime.datetime.now().isoformat()

    # -- Database -------------------------------------------------------
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in transformed.error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in transformed.api_latency.items():
        avg = sum(times) / len(times)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()

    # -- HTML report ----------------------------------------------------
    html = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    html += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in transformed.error_counts.items():
        html += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    html += "</ul>\n"

    html += "<h2>API Latency</h2>\n<table border='1'>\n"
    html += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, times in transformed.api_latency.items():
        avg = round(sum(times) / len(times), 1)
        html += f"<tr><td>{endpoint}</td><td>{avg}</td></tr>\n"
    html += "</table>\n"

    html += "<h2>Active Sessions</h2>\n"
    html += f"<p>{transformed.active_sessions} user(s) currently active</p>\n"
    html += "</body>\n</html>"

    Path("report.html").write_text(html, encoding="utf-8")

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    config = load_config()

    # If the log file is missing, write a small fixture so the script
    # produces meaningful output when executed standalone.
    log_path = Path(config.log_file)
    if not log_path.exists():
        log_path.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n",
            encoding="utf-8",
        )

    extracted = extract(config.log_file)
    transformed = transform(extracted)
    load(transformed, config)


if __name__ == "__main__":
    main()