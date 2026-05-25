import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

# Configuration derived from environment variables with safe defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Compiled regular expression patterns for high-performance and robust log parsing
LOG_LINE_PATTERN: re.Pattern = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<level>[A-Z]+)\s+(?P<payload>.*)$"
)
USER_ACTION_PATTERN: re.Pattern = re.compile(
    r"^User\s+(?P<uid>\w+)\s+(?P<action>.*)$"
)
API_CALL_PATTERN: re.Pattern = re.compile(
    r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<ms>\d+)ms)?$"
)


@dataclass
class ExtractedLogData:
    """A data container representing the raw elements parsed from the log file.

    Attributes:
        errors_and_actions: A collection of events (errors, user logins, and warnings).
        sessions: A state tracking dictionary of active user session timestamps key by user ID.
        api_calls: A collection of individual API latency records.
    """
    errors_and_actions: List[Dict[str, Any]]
    sessions: Dict[str, str]
    api_calls: List[Dict[str, Any]]


@dataclass
class TransformedMetrics:
    """A data container representing transformed, aggregated metrics.

    Attributes:
        error_counts: Aggregated counts of error messages.
        endpoint_stats: Grouped collections of API latency times.
        active_session_count: Total active user sessions at the end of the log period.
    """
    error_counts: Dict[str, int]
    endpoint_stats: Dict[str, List[int]]
    active_session_count: int


def extract_log_data(log_file_path: str) -> ExtractedLogData:
    """Reads the log file line by line and parses details using regex.

    This function represents the Extract phase of the ETL pipeline.

    Args:
        log_file_path: File system path to the log file.

    Returns:
        An ExtractedLogData containing the parsed log elements.
    """
    errors_and_actions: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return ExtractedLogData(errors_and_actions, sessions, api_calls)

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            line_match = LOG_LINE_PATTERN.match(stripped)
            if not line_match:
                continue

            dt: str = line_match.group("dt")
            level: str = line_match.group("level")
            payload: str = line_match.group("payload")

            if level == "ERROR":
                errors_and_actions.append({"d": dt, "t": "ERR", "m": payload.strip()})

            elif level == "INFO":
                user_match = USER_ACTION_PATTERN.match(payload)
                if user_match:
                    uid: str = user_match.group("uid")
                    action: str = user_match.group("action").strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    errors_and_actions.append({"d": dt, "t": "USR", "u": uid, "a": action})
                    continue

                api_match = API_CALL_PATTERN.match(payload)
                if api_match:
                    endpoint: str = api_match.group("endpoint")
                    ms_str: Optional[str] = api_match.group("ms")
                    ms: int = int(ms_str) if ms_str else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": ms})

            elif level == "WARN":
                errors_and_actions.append({"d": dt, "t": "WARN", "m": payload.strip()})

    return ExtractedLogData(errors_and_actions, sessions, api_calls)


def transform_metrics(extracted_data: ExtractedLogData) -> TransformedMetrics:
    """Transforms raw log event lists into summarized and aggregated metrics.

    This function represents the Transform phase of the ETL pipeline.

    Args:
        extracted_data: Raw parsed log records.

    Returns:
        A TransformedMetrics holding aggregated data.
    """
    error_counts: Dict[str, int] = {}
    for event in extracted_data.errors_and_actions:
        if event["t"] == "ERR":
            msg: str = event["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in extracted_data.api_calls:
        ep: str = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    return TransformedMetrics(
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        active_session_count=len(extracted_data.sessions),
    )


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """Saves aggregated metrics to the SQLite database.

    This function represents the Load phase of the ETL pipeline.
    All database operations are parameterized to defend against SQL Injection.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Summary dictionary mapping error messages to count.
        endpoint_stats: Aggregated dictionary of endpoint latency measurements.
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

        current_time: str = str(datetime.datetime.now())

        # Parameterized queries - clean and safe from SQL Injection
        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (current_time, msg, count),
            )

        for ep, times in endpoint_stats.items():
            avg: float = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (current_time, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def generate_html_report(
    report_path: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_session_count: int,
) -> None:
    """Generates a structured system report in HTML format.

    Args:
        report_path: Destination path for the HTML file.
        error_counts: Aggregated error metrics.
        endpoint_stats: API latency metric lists.
        active_session_count: Current user active session count.
    """
    out: str = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg: float = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution orchestrator of the parsing and aggregation pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # Extract
    extracted_data: ExtractedLogData = extract_log_data(LOG_FILE)

    # Transform
    metrics: TransformedMetrics = transform_metrics(extracted_data)

    # Load
    load_to_database(DB_PATH, metrics.error_counts, metrics.endpoint_stats)
    generate_html_report(
        "report.html",
        metrics.error_counts,
        metrics.endpoint_stats,
        metrics.active_session_count,
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fixture_f:
            fixture_f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fixture_f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fixture_f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fixture_f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fixture_f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fixture_f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
