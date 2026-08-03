"""Server-log pipeline: parse, aggregate, persist, and report.

Refactored from the original single-function ``pipeline.py`` into a
Extract -> Transform -> Load pipeline with:

- environment-driven configuration (no hardcoded paths or credentials),
- regex-based log parsing instead of fragile ``str.split``,
- parameterized SQL queries (no string interpolation),
- typed, documented, single-purpose functions.

Run:

    LOG_FILE=server.log DB_PATH=metrics.db python pipeline_refactored.py

All configuration is read from the environment; see ``load_config``.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Log line: "<date> <time> <LEVEL> <message>" (e.g. "2024-01-01 12:00:00 INFO ...").
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN|DEBUG)\s+(?P<message>.*)$"
)
# Sub-line formats for INFO payloads.
_USER_ACTION_RE = re.compile(r"User (?P<user_id>\S+) (?P<action>.+)$")
_API_CALL_RE = re.compile(r"API (?P<endpoint>\S+)(?: took (?P<duration_ms>\d+)ms)?$")

SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@dataclass(frozen=True)
class Config:
    """Runtime configuration read from the environment."""

    log_file: str
    db_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def load_config() -> Config:
    """Read all configuration from environment variables.

    DB_HOST, DB_PORT, DB_USER and DB_PASS describe the remote server the
    original script connected to; they are kept for parity. The local SQLite
    connection does not authenticate, so DB_PASS is never used by the script
    itself.
    """
    return Config(
        log_file=os.getenv("LOG_FILE", "server.log"),
        db_path=os.getenv("DB_PATH", "metrics.db"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", ""),
        db_pass=os.getenv("DB_PASS", ""),
    )


def seed_sample_log(log_path: Path) -> None:
    """Write a small demo log at ``log_path`` if it does not already exist."""
    if log_path.exists():
        return
    log_path.write_text(SAMPLE_LOG, encoding="utf-8")


def extract_logs(log_path: Path) -> list[dict[str, str]]:
    """Parse every line of ``log_path`` into a structured record.

    Lines that do not match the expected log format are skipped, mirroring the
    original script's silent handling of unrecognized input. A missing file
    yields an empty list so the rest of the pipeline can still run.
    """
    records: list[dict[str, str]] = []
    try:
        with open(log_path, encoding="utf-8") as handle:
            for line in handle:
                match = _LOG_LINE_RE.match(line)
                if match is None:
                    continue
                records.append(match.groupdict())
    except FileNotFoundError:
        print(f"WARNING: log file not found: {log_path}")
    return records


def transform_logs(
    records: list[dict[str, str]],
) -> tuple[dict[str, int], dict[str, float], int]:
    """Aggregate raw records into report-ready metrics.

    Returns ``(error_counts, avg_latency_ms, active_session_count)`` where
    error counts are keyed by message text and latency is the per-endpoint
    average in milliseconds. Session state is tracked as users log in/out.
    WARN and non-User/API INFO lines are recognized but do not contribute to
    the report, matching the original output.
    """
    error_counts: dict[str, int] = {}
    latency_samples: dict[str, list[int]] = {}
    active_sessions: dict[str, str] = {}

    for record in records:
        level = record["level"]
        message = record["message"].strip()

        if level == "ERROR":
            error_counts[message] = error_counts.get(message, 0) + 1
            continue

        if level != "INFO":
            continue

        user_match = _USER_ACTION_RE.search(message)
        if user_match is not None:
            user_id = user_match.group("user_id")
            action = user_match.group("action")
            if "logged in" in action:
                active_sessions[user_id] = record["timestamp"]
            elif "logged out" in action and user_id in active_sessions:
                del active_sessions[user_id]
            continue

        api_match = _API_CALL_RE.search(message)
        if api_match is not None:
            endpoint = api_match.group("endpoint")
            duration_ms = api_match.group("duration_ms")
            latency_samples.setdefault(endpoint, []).append(
                int(duration_ms) if duration_ms is not None else 0
            )

    avg_latency_ms = {
        endpoint: sum(samples) / len(samples)
        for endpoint, samples in latency_samples.items()
    }
    return error_counts, avg_latency_ms, len(active_sessions)


def load_to_db(
    config: Config,
    error_counts: dict[str, int],
    avg_latency_ms: dict[str, float],
) -> None:
    """Persist aggregated metrics into the SQLite database at ``config.db_path``.

    All values are bound as query parameters — never interpolated into the SQL
    text — so log-derived data cannot alter the statements being executed.
    """
    conn = sqlite3.connect(config.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors "
            "(dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics "
            "(dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        timestamp = datetime.datetime.now().isoformat(sep=" ")
        cursor.executemany(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            [(timestamp, message, count) for message, count in error_counts.items()],
        )
        cursor.executemany(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            [(timestamp, endpoint, avg) for endpoint, avg in avg_latency_ms.items()],
        )
        conn.commit()
    finally:
        conn.close()


def write_report(
    error_counts: dict[str, int],
    avg_latency_ms: dict[str, float],
    active_session_count: int,
    output_path: Path = Path("report.html"),
) -> None:
    """Write the HTML report to ``output_path``.

    The report keeps the original sections — error summary, API latency table,
    active session count — and HTML-escapes log-derived text so malformed
    messages cannot inject markup.
    """
    parts = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for message, count in error_counts.items():
        parts.append(
            f"<li><b>{html.escape(message)}</b>: {count} occurrences</li>"
        )
    parts.extend(
        [
            "</ul>",
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )
    for endpoint, avg in avg_latency_ms.items():
        parts.append(
            f"<tr><td>{html.escape(endpoint)}</td>"
            f"<td>{round(avg, 1)}</td></tr>"
        )
    parts.extend(
        [
            "</table>",
            "<h2>Active Sessions</h2>",
            f"<p>{active_session_count} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    """Run the full Extract -> Transform -> Load pipeline."""
    config = load_config()
    log_path = Path(config.log_file)
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}")
    seed_sample_log(log_path)
    records = extract_logs(log_path)
    error_counts, avg_latency_ms, active_session_count = transform_logs(records)
    load_to_db(config, error_counts, avg_latency_ms)
    write_report(error_counts, avg_latency_ms, active_session_count)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
