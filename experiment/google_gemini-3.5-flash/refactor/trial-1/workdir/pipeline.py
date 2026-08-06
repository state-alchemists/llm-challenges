"""Pipeline module to process server logs and generate metrics report."""

from dataclasses import dataclass
import datetime
import os
import re
import sqlite3

# Define compiled regular expression patterns for performance and reuse
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"User\s+(\S+)\s+(.*)")
API_PATTERN = re.compile(r"API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


@dataclass(frozen=True, slots=True)
class LogLine:
    """Representation of a single parsed log line."""

    dt: str
    level: str
    content: str


def extract_log_lines(log_file_path: str) -> list[LogLine]:
    """Extract and parse log lines from the given file path using regular expressions.

    Args:
        log_file_path: Path to the log file.

    Returns:
        A list of parsed LogLine objects containing datetime, level, and message content.
    """
    entries: list[LogLine] = []
    if not os.path.exists(log_file_path):
        return entries

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line_raw in f:
            line = line_raw.strip()
            match = LOG_LINE_PATTERN.match(line)
            if match:
                dt, lvl, rest = match.groups()
                entries.append(LogLine(dt=dt, level=lvl, content=rest))
    return entries


def _update_sessions(
    uid: str, action: str, dt: str, sessions: dict[str, str]
) -> None:
    """Helper to update user sessions based on login/logout actions."""
    if "logged in" in action:
        sessions[uid] = dt
    elif "logged out" in action and uid in sessions:
        sessions.pop(uid)


def _process_info_entry(
    entry_dt: str,
    content: str,
    sessions: dict[str, str],
    api_calls: dict[str, list[int]],
) -> None:
    """Helper to process INFO log lines."""
    if "User" in content:
        user_match = USER_PATTERN.search(content)
        if user_match:
            uid, action = user_match.groups()
            _update_sessions(uid, action, entry_dt, sessions)
    elif "API" in content:
        api_match = API_PATTERN.search(content)
        if api_match:
            endpoint, dur_str = api_match.groups()
            duration = int(dur_str) if dur_str else 0
            api_calls.setdefault(endpoint, []).append(duration)


def transform_log_data(
    entries: list[LogLine],
) -> tuple[dict[str, int], dict[str, list[int]], int]:
    """Transform extracted log entries into aggregated metrics.

    Args:
        entries: A list of LogLine objects to transform.

    Returns:
        A tuple containing:
        - A dictionary of error messages to occurrence counts.
        - A dictionary of API endpoints to lists of latency durations (ms).
        - The count of currently active sessions.
    """
    errors: dict[str, int] = {}
    api_calls: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for entry in entries:
        if entry.level == "ERROR":
            errors[entry.content] = errors.get(entry.content, 0) + 1
        elif entry.level == "INFO":
            _process_info_entry(entry.dt, entry.content, sessions, api_calls)

    return errors, api_calls, len(sessions)


def load_to_database(
    errors: dict[str, int], api_calls: dict[str, list[int]], db_path: str
) -> None:
    """Load the transformed metrics into the SQLite database.

    Args:
        errors: Dictionary of error messages and counts.
        api_calls: Dictionary of endpoints and list of durations.
        db_path: Path to the SQLite database file.
    """
    now_str = str(datetime.datetime.now())

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in errors.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, times in api_calls.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )
        conn.commit()


def generate_report(
    errors: dict[str, int],
    api_calls: dict[str, list[int]],
    active_session_count: int,
    report_path: str,
) -> None:
    """Generate HTML report representing current system status.

    Args:
        errors: Dictionary of error messages and counts.
        api_calls: Dictionary of endpoints and list of durations.
        active_session_count: Number of active sessions.
        report_path: Path to save the generated HTML report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_calls.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Main execution function to run the log processing pipeline."""
    db_path = os.getenv("DB_PATH", "metrics.db")
    log_file = os.getenv("LOG_FILE", "server.log")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "admin")
    _db_pass = os.getenv("DB_PASS", "password123")

    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    entries = extract_log_lines(log_file)
    errors, api_calls, active_sessions = transform_log_data(entries)
    load_to_database(errors, api_calls, db_path)
    generate_report(errors, api_calls, active_sessions, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    run_pipeline()
