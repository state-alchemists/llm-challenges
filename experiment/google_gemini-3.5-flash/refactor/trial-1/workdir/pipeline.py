import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

# Configuration loaded from Environment Variables with original defaults as fallbacks
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "")

# Regular Expressions for parsing log entries
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)
USER_PATTERN = re.compile(r"^User (\S+) (.*)$")
API_PATTERN = re.compile(r"^API (\S+)(?: took (\d+)ms)?")


@dataclass(frozen=True)
class LogEntry:
    """Represents a parsed structured log entry."""
    timestamp: str
    level: str
    message: str


class LogTransformer:
    """Transforms raw log entries into structured analysis metrics."""

    def __init__(self) -> None:
        self.errors: dict[str, int] = {}
        self.sessions: dict[str, str] = {}
        self.endpoint_durations: dict[str, list[int]] = {}

    def process_entry(self, entry: LogEntry) -> None:
        """Processes a single LogEntry, updating metrics accordingly."""
        if entry.level == "ERROR":
            self._process_error(entry)
        elif entry.level == "INFO":
            self._process_info(entry)

    def _process_error(self, entry: LogEntry) -> None:
        self.errors[entry.message] = self.errors.get(entry.message, 0) + 1

    def _process_info(self, entry: LogEntry) -> None:
        user_match = USER_PATTERN.match(entry.message)
        if user_match:
            self._process_user_session(
                user_match.group(1),
                user_match.group(2),
                entry.timestamp
            )
            return

        api_match = API_PATTERN.match(entry.message)
        if api_match:
            self._process_api_call(api_match.group(1), api_match.group(2))

    def _process_user_session(
        self, uid: str, action: str, timestamp: str
    ) -> None:
        if "logged in" in action:
            self.sessions[uid] = timestamp
        elif "logged out" in action:
            self.sessions.pop(uid, None)

    def _process_api_call(
        self, endpoint: str, duration_str: Optional[str]
    ) -> None:
        duration = int(duration_str) if duration_str else 0
        self.endpoint_durations.setdefault(endpoint, []).append(duration)


def write_default_logs(log_file_path: str) -> None:
    """Writes default sample log records to the specified file path."""
    default_content = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write(default_content)


def extract_log_lines(file_path: str) -> list[str]:
    """Reads the raw lines from a log file.

    Args:
        file_path: The file path of the server log.

    Returns:
        A list of raw log line strings. If the file does not exist, returns an
        empty list.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parses a raw log line into a LogEntry dataclass.

    Args:
        line: The raw log line string.

    Returns:
        A LogEntry object if parsing succeeds, otherwise None.
    """
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None
    return LogEntry(
        timestamp=match.group(1),
        level=match.group(2),
        message=match.group(3)
    )


def load_metrics_to_db(
    db_path: str,
    errors: dict[str, int],
    endpoint_durations: dict[str, list[int]]
) -> None:
    """Loads the parsed metrics into the SQLite database safely using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        errors: A dictionary mapping error messages to their occurrence counts.
        endpoint_durations: A dictionary mapping endpoints to list of response
        times.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in errors.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count)
            )

        for ep, times in endpoint_durations.items():
            if times:
                avg = sum(times) / len(times)
                cursor.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (now_str, ep, avg)
                )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    report_path: str,
    errors: dict[str, int],
    endpoint_durations: dict[str, list[int]],
    active_sessions: dict[str, str]
) -> None:
    """Generates the HTML system report with the calculated metrics.

    Args:
        report_path: Path where the HTML report file will be written.
        errors: A dictionary of errors and their counts.
        endpoint_durations: A dictionary of endpoints and their durations.
        active_sessions: A dictionary of active sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_durations.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{str(round(avg, 1))}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{str(len(active_sessions))} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Runs the log processing ETL pipeline."""
    if not os.path.exists(LOG_FILE):
        write_default_logs(LOG_FILE)

    # Extract
    log_lines = extract_log_lines(LOG_FILE)

    # Transform
    transformer = LogTransformer()
    for line in log_lines:
        entry = parse_log_line(line)
        if entry:
            transformer.process_entry(entry)

    # Load
    load_metrics_to_db(DB_PATH, transformer.errors, transformer.endpoint_durations)
    generate_html_report(
        "report.html",
        transformer.errors,
        transformer.endpoint_durations,
        transformer.sessions
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
