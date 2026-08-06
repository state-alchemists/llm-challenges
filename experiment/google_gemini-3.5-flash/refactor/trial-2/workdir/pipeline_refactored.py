import datetime
import os
import re
import sqlite3
from dataclasses import dataclass

# Configuration using environment variables with defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Compiled regex patterns for log line parsing
LOG_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
USER_PATTERN: re.Pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN: re.Pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class RawLogLine:
    """Container for a parsed raw log line."""

    timestamp: str
    level: str
    content: str


@dataclass(frozen=True, slots=True)
class LogMetrics:
    """Container for the metrics aggregated from log parsing."""

    errors: dict[str, int]
    api_latency: dict[str, list[int]]
    active_sessions: dict[str, str]


def extract_log_lines(log_file_path: str) -> list[str]:
    """Reads raw log lines from the specified file if it exists.

    Args:
        log_file_path: Path to the log file.

    Returns:
        A list of raw log lines.
    """
    if not os.path.exists(log_file_path):
        return []
    with open(log_file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def parse_raw_line(line: str) -> RawLogLine | None:
    """Parses a single raw log line into a RawLogLine object.

    Args:
        line: A single raw log line.

    Returns:
        A RawLogLine object if parsing succeeded, else None.
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None
    dt, lvl, content = match.groups()
    return RawLogLine(timestamp=dt, level=lvl, content=content)


def _process_info_level(
    entry: RawLogLine,
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
) -> None:
    """Helper to process log entries with INFO level.

    Args:
        entry: The parsed RawLogLine entry.
        api_latency: In-out dict for tracking API latencies.
        active_sessions: In-out dict for tracking active sessions.
    """
    user_match = USER_PATTERN.match(entry.content)
    if user_match:
        uid, action = user_match.groups()
        if "logged in" in action:
            active_sessions[uid] = entry.timestamp
        elif "logged out" in action:
            active_sessions.pop(uid, None)

    api_match = API_PATTERN.match(entry.content)
    if api_match:
        endpoint, dur_str = api_match.groups()
        dur = int(dur_str) if dur_str else 0
        api_latency.setdefault(endpoint, []).append(dur)


def _process_parsed_entry(
    entry: RawLogLine,
    errors: dict[str, int],
    api_latency: dict[str, list[int]],
    active_sessions: dict[str, str],
) -> None:
    """Updates metric collections based on a parsed entry.

    Args:
        entry: The parsed RawLogLine entry.
        errors: In-out dict for error occurrences.
        api_latency: In-out dict for tracking API latencies.
        active_sessions: In-out dict for tracking active sessions.
    """
    if entry.level == "ERROR":
        errors[entry.content] = errors.get(entry.content, 0) + 1
    elif entry.level == "INFO":
        _process_info_level(entry, api_latency, active_sessions)


def transform_log_data(lines: list[str]) -> LogMetrics:
    """Parses and aggregates metrics from raw log lines.

    Args:
        lines: List of raw log lines.

    Returns:
        LogMetrics data structure containing aggregated info.
    """
    errors: dict[str, int] = {}
    api_latency: dict[str, list[int]] = {}
    active_sessions: dict[str, str] = {}

    for line in lines:
        parsed = parse_raw_line(line)
        if not parsed:
            continue
        _process_parsed_entry(parsed, errors, api_latency, active_sessions)

    return LogMetrics(
        errors=errors,
        api_latency=api_latency,
        active_sessions=active_sessions,
    )


def load_metrics_to_db(db_path: str, metrics: LogMetrics) -> None:
    """Saves aggregated metrics to SQLite database using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        metrics: Aggregated log metrics.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    now_str = str(datetime.datetime.now())

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in metrics.errors.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in metrics.api_latency.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (now_str, ep, avg),
                )
        conn.commit()


def load_metrics_to_html_report(report_path: str, metrics: LogMetrics) -> None:
    """Generates the HTML report containing the aggregated metrics.

    Args:
        report_path: Path where the HTML report will be written.
        metrics: Aggregated log metrics.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics.api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(metrics.active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution function for the logging pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    lines = extract_log_lines(LOG_FILE)
    metrics = transform_log_data(lines)
    load_metrics_to_db(DB_PATH, metrics)
    load_metrics_to_html_report("report.html", metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
