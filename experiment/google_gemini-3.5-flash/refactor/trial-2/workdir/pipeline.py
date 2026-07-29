"""System Report ETL Pipeline.

Processes server logs, aggregates error counts and API latency metrics,
stores them in a SQLite database safely, and generates an HTML report.
"""

from dataclasses import dataclass
import datetime
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

# Regular expression patterns for log parsing
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class Config:
    """Configuration class loading options from environment variables with sensible defaults."""

    db_path: Path
    log_file: Path
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    report_file: Path

    @classmethod
    def from_env(cls) -> "Config":
        """Loads configuration from environment variables."""
        db_port_str = os.getenv("DB_PORT", "5432")
        try:
            db_port = int(db_port_str)
        except ValueError:
            db_port = 5432

        return cls(
            db_path=Path(os.getenv("DB_PATH", "metrics.db")),
            log_file=Path(os.getenv("LOG_FILE", "server.log")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=db_port,
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
            report_file=Path(os.getenv("REPORT_FILE", "report.html")),
        )


@dataclass(frozen=True, slots=True)
class LogData:
    """Data structure containing parsed log data."""

    errors: list[dict[str, Any]]
    api_calls: list[dict[str, Any]]
    sessions: dict[str, str]
    warnings: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TransformedMetrics:
    """Structured metrics produced by transforming raw log data."""

    error_counts: dict[str, int]
    api_averages: dict[str, float]
    active_sessions_count: int


def extract_log_data(log_file_path: Path) -> LogData:
    """Reads a log file and extracts structured LogData using regular expressions.

    Args:
        log_file_path: Path to the log file.

    Returns:
        LogData: Containing lists of errors, api_calls, warnings, and active sessions.
    """
    errors: list[dict[str, Any]] = []
    api_calls: list[dict[str, Any]] = []
    sessions: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []

    if not log_file_path.exists():
        return LogData(
            errors=errors,
            api_calls=api_calls,
            sessions=sessions,
            warnings=warnings,
        )

    with log_file_path.open("r", encoding="utf-8") as file:
        for line in file:
            line_match = LOG_LINE_PATTERN.match(line.strip())
            if not line_match:
                continue

            dt, lvl, rest = line_match.groups()

            if lvl == "ERROR":
                errors.append({"d": dt, "m": rest.strip()})

            elif lvl == "INFO":
                user_match = USER_PATTERN.match(rest)
                if user_match:
                    uid, action = user_match.groups()
                    action = action.strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)

                api_match = API_PATTERN.match(rest)
                if api_match:
                    endpoint, dur = api_match.groups()
                    ms = int(dur) if dur is not None else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": ms})

            elif lvl == "WARN":
                warnings.append({"d": dt, "m": rest.strip()})

    return LogData(
        errors=errors,
        api_calls=api_calls,
        sessions=sessions,
        warnings=warnings,
    )


def transform_metrics(log_data: LogData) -> TransformedMetrics:
    """Transforms raw log data into structured metrics for errors and API latency.

    Args:
        log_data: Parsed raw log data from Extract phase.

    Returns:
        TransformedMetrics: Aggregated counts and latency averages.
    """
    error_counts: dict[str, int] = {}
    for err in log_data.errors:
        msg = err["m"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: dict[str, list[int]] = {}
    for call in log_data.api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_averages: dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        api_averages[ep] = sum(times) / len(times) if times else 0.0

    return TransformedMetrics(
        error_counts=error_counts,
        api_averages=api_averages,
        active_sessions_count=len(log_data.sessions),
    )


def load_to_database(db_path: Path, metrics: TransformedMetrics) -> None:
    """Saves the transformed metrics to the SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database.
        metrics: Transformed aggregates to save.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        current_time = str(datetime.datetime.now())

        for msg, count in metrics.error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (current_time, msg, count),
            )

        for ep, avg in metrics.api_averages.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (current_time, ep, avg),
            )
        conn.commit()
    finally:
        conn.close()


def generate_html_report(report_path: Path, metrics: TransformedMetrics) -> None:
    """Generates an HTML report summarizing system metrics.

    Args:
        report_path: Path to write the HTML report to.
        metrics: Transformed aggregates.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with report_path.open("w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrates the Extract, Transform, and Load (ETL) pipeline."""
    config = Config.from_env()

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    # 1. Extract
    log_data = extract_log_data(config.log_file)

    # 2. Transform
    metrics = transform_metrics(log_data)

    # 3. Load
    load_to_database(config.db_path, metrics)
    generate_html_report(config.report_file, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    _config = Config.from_env()
    if not _config.log_file.exists():
        with _config.log_file.open("w", encoding="utf-8") as _f:
            _f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            _f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            _f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            _f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            _f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            _f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
