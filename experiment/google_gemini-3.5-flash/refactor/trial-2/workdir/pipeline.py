import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field

# Configuration from environment variables
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")

# Regular expressions for log parsing
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class LogAnalysisResult:
    """Contains structured metrics extracted from raw log analysis."""

    errors: dict[str, int] = field(default_factory=dict)
    endpoint_stats: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


def extract_log_lines(file_path: str) -> list[str]:
    """
    Reads all raw lines from the log file.

    Args:
        file_path: Path to the log file.

    Returns:
        A list of raw log lines. If the file does not exist, returns an empty list.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def _parse_info_msg(
    msg: str,
    dt: str,
    active_sessions: dict[str, str],
    endpoint_stats: dict[str, list[int]],
) -> None:
    """Parses informational message content for user actions and API latencies."""
    user_match = USER_PATTERN.match(msg)
    if user_match:
        uid, action = user_match.groups()
        if "logged in" in action:
            active_sessions[uid] = dt
        elif "logged out" in action and uid in active_sessions:
            active_sessions.pop(uid)
        return

    api_match = API_PATTERN.match(msg)
    if api_match:
        endpoint, dur_str = api_match.groups()
        dur = int(dur_str) if dur_str is not None else 0
        endpoint_stats.setdefault(endpoint, []).append(dur)


def transform_log_lines(lines: list[str]) -> LogAnalysisResult:
    """
    Parses raw log lines and transforms them into structured data.

    Args:
        lines: A list of raw log lines.

    Returns:
        A LogAnalysisResult containing parsed errors, endpoint stats, and active sessions.
    """
    errors: dict[str, int] = {}
    endpoint_stats: dict[str, list[int]] = {}
    active_sessions: dict[str, str] = {}

    for line in lines:
        match = LOG_PATTERN.match(line.strip())
        if not match:
            continue

        dt, level, msg = match.groups()

        if level == "ERROR":
            errors[msg] = errors.get(msg, 0) + 1
        elif level == "INFO":
            _parse_info_msg(msg, dt, active_sessions, endpoint_stats)

    return LogAnalysisResult(
        errors=errors,
        endpoint_stats=endpoint_stats,
        active_sessions=active_sessions,
    )


def save_to_database(db_path: str, result: LogAnalysisResult) -> None:
    """Saves error summary and API metrics to the SQLite database."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        now_str = str(datetime.datetime.now())
        for msg, count in result.errors.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )
        for ep, times in result.endpoint_stats.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )
        conn.commit()
    finally:
        conn.close()


def generate_html_report(report_path: str, result: LogAnalysisResult) -> None:
    """Generates an HTML report containing extracted server log metrics."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in result.errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in result.endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(result.active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """Orchestrates the Extract, Transform, and Load (ETL) pipeline."""
    lines = extract_log_lines(LOG_FILE)
    result = transform_log_lines(lines)
    save_to_database(DB_PATH, result)
    generate_html_report("report.html", result)
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
