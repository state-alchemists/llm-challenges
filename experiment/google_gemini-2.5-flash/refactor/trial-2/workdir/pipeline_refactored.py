import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True, slots=True)
class Config:
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime.datetime
    level: str
    message: str
    user_id: Optional[str] = None
    action: Optional[str] = None
    endpoint: Optional[str] = None
    duration_ms: Optional[int] = None


def load_config() -> Config:
    """Loads configuration from environment variables."""
    db_path = os.environ.get("DB_PATH", "metrics.db")
    log_file = os.environ.get("LOG_FILE", "server.log")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", "5432"))
    db_user = os.environ.get("DB_USER", "admin")
    db_pass = os.environ.get("DB_PASS", "password123")
    return Config(db_path, log_file, db_host, db_port, db_user, db_pass)


def parse_log_line(line: str) -> Optional[LogEntry]:
    """
    Parses a single log line using regex and returns a LogEntry object.
    """
    log_pattern = re.compile(
        r"""^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2}) """
        r"""(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) """
        r"""(?P<level>INFO|ERROR|WARN) """
        r"""((User (?P<user_id>\d+) (?P<action>.+))|"""
        r"""(API (?P<endpoint>/\S+) took (?P<duration>\d+)ms)|"""
        r"""(?P<message>.+))$"""
    )
    match = log_pattern.match(line)
    if not match:
        return None

    data = match.groupdict()
    timestamp_str = f"{data['year']}-{data['month']}-{data['day']} {data['hour']}:{data['minute']}:{data['second']}"
    timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    level = data["level"]
    message = data["message"].strip() if data["message"] else ""

    if level == "INFO":
        if data["user_id"]:
            return LogEntry(
                timestamp=timestamp,
                level=level,
                message=f"User {data['user_id']} {data['action']}",
                user_id=data["user_id"],
                action=data["action"].strip(),
            )
        elif data["endpoint"]:
            return LogEntry(
                timestamp=timestamp,
                level=level,
                message=f"API {data['endpoint']} took {data['duration']}ms",
                endpoint=data["endpoint"],
                duration_ms=int(data["duration"]),
            )
    elif level == "ERROR" or level == "WARN":
        return LogEntry(timestamp=timestamp, level=level, message=message)
    return None


def read_log_file(log_file_path: str) -> Iterable[LogEntry]:
    """
    Reads the log file line by line, parses each line, and yields LogEntry objects.
    """
    if not os.path.exists(log_file_path):
        return

    with open(log_file_path, "r") as f:
        for line in f:
            log_entry = parse_log_line(line)
            if log_entry:
                yield log_entry


def analyze_errors(log_entries: Iterable[LogEntry]) -> Dict[str, int]:
    """
    Analyzes log entries to count occurrences of each unique error message.
    """
    error_summary: Dict[str, int] = {}
    for entry in log_entries:
        if entry.level == "ERROR":
            error_summary[entry.message] = error_summary.get(entry.message, 0) + 1
    return error_summary


def analyze_api_latency(log_entries: Iterable[LogEntry]) -> Dict[str, List[int]]:
    """
    Analyzes log entries to collect all latencies for each API endpoint.
    """
    api_latency_stats: Dict[str, List[int]] = {}
    for entry in log_entries:
        if entry.level == "INFO" and entry.endpoint and entry.duration_ms is not None:
            api_latency_stats.setdefault(entry.endpoint, []).append(entry.duration_ms)
    return api_latency_stats


def track_active_sessions(log_entries: Iterable[LogEntry]) -> int:
    """
    Tracks active user sessions based on login and logout events.
    """
    sessions: Dict[str, datetime.datetime] = {}
    for entry in log_entries:
        if entry.level == "INFO" and entry.user_id and entry.action:
            if "logged in" in entry.action:
                sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in sessions:
                sessions.pop(entry.user_id)
    return len(sessions)


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Establishes and returns a SQLite database connection."""
    return sqlite3.connect(db_path)


def initialize_database(conn: sqlite3.Connection) -> None:
    """Initializes database tables if they do not exist."""
    c = conn.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()


def insert_error_summary(
    conn: sqlite3.Connection, error_summary: Dict[str, int]
) -> None:
    """Inserts error counts into the errors table using parameterized queries."""
    c = conn.cursor()
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )
    conn.commit()


def insert_api_metrics(
    conn: sqlite3.Connection, api_latency_stats: Dict[str, List[int]]
) -> None:
    """
    Calculates average latencies and inserts into api_metrics table using parameterized queries.
    """
    c = conn.cursor()
    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )
    conn.commit()


def generate_html_report(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
    active_sessions: int,
) -> str:
    """Constructs the HTML report string."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out


def write_report_file(report_content: str, output_path: str) -> None:
    """Writes the HTML report to a file."""
    with open(output_path, "w") as f:
        f.write(report_content)


def main():
    """Main function to orchestrate the log processing and report generation."""
    config = load_config()

    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    log_entries = list(read_log_file(config.log_file))

    error_summary = analyze_errors(log_entries)
    api_latency_stats = analyze_api_latency(log_entries)
    active_sessions = track_active_sessions(log_entries)

    conn = get_db_connection(config.db_path)
    initialize_database(conn)
    insert_error_summary(conn, error_summary)
    insert_api_metrics(conn, api_latency_stats)
    conn.close()

    html_report = generate_html_report(
        error_summary, api_latency_stats, active_sessions
    )
    write_report_file(html_report, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # For demonstration, create a dummy log file if it doesn't exist
    if not os.path.exists(os.environ.get("LOG_FILE", "server.log")):
        with open(os.environ.get("LOG_FILE", "server.log"), "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
