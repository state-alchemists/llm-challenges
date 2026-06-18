import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple

# Configuration loaded from environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: str = os.getenv("DB_PORT", "5432")
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Compiled regular expressions for parsing log entries
# Matches format: YYYY-MM-DD HH:MM:SS LEVEL MESSAGE
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)

# Sub-patterns for parsing log level INFO payloads
USER_PATTERN = re.compile(r"^User\s+(\S+)\s+(.*)$")
API_PATTERN = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def extract_log_lines(log_file_path: str) -> List[str]:
    """Reads and extracts all raw lines from the log file.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of raw string lines from the log file, or an empty list
        if the file does not exist.
    """
    if not os.path.exists(log_file_path):
        return []

    with open(log_file_path, "r", encoding="utf-8") as f:
        return f.readlines()


def transform_log_lines(
    lines: List[str],
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Transforms raw log lines into structured metrics using regex.

    Args:
        lines: A list of raw log lines.

    Returns:
        A tuple containing:
          - A dictionary of error messages mapped to their occurrence count.
          - A dictionary of API endpoints mapped to lists of latency values in ms.
          - A dictionary representing active user sessions (user ID -> login time).
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for line in lines:
        line_match = LOG_LINE_PATTERN.match(line.strip())
        if not line_match:
            continue

        dt: str = line_match.group(1)
        lvl: str = line_match.group(2)
        payload: str = line_match.group(3)

        if lvl == "ERROR":
            error_counts[payload] = error_counts.get(payload, 0) + 1

        elif lvl == "INFO":
            # Check User action matching
            user_match = USER_PATTERN.match(payload)
            if user_match:
                uid: str = user_match.group(1)
                action: str = user_match.group(2)
                if "logged in" in action:
                    active_sessions[uid] = dt
                elif "logged out" in action and uid in active_sessions:
                    active_sessions.pop(uid)

            # Check API call matching
            api_match = API_PATTERN.match(payload)
            if api_match:
                endpoint: str = api_match.group(1)
                dur_str: str | None = api_match.group(2)
                dur: int = int(dur_str) if dur_str is not None else 0
                api_latencies.setdefault(endpoint, []).append(dur)

        # Warnings and other log levels are parsed but not aggregated for the report.

    return error_counts, api_latencies, active_sessions


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """Loads metrics into the SQLite database securely using parameterized queries.

    Args:
        db_path: The database file path.
        error_counts: Aggregated error message counts.
        api_latencies: Endpoint latency lists.
    """
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

        current_time = str(datetime.datetime.now())

        # Insert errors safely
        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (current_time, msg, count),
            )

        # Insert API metrics safely
        for ep, times in api_latencies.items():
            if times:
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics VALUES (?, ?, ?)",
                    (current_time, ep, avg),
                )

        conn.commit()
    finally:
        conn.close()


def load_to_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
) -> None:
    """Generates an HTML report summarizing the parsed server metrics.

    Args:
        report_path: Path where the HTML report will be written.
        error_counts: Aggregated error message counts.
        api_latencies: Endpoint latency lists.
        active_sessions: Representing active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def run_pipeline() -> None:
    """Orchestrates the entire log processing ETL pipeline."""
    raw_lines = extract_log_lines(LOG_FILE)
    error_counts, api_latencies, active_sessions = transform_log_lines(raw_lines)
    load_to_database(DB_PATH, error_counts, api_latencies)
    load_to_report("report.html", error_counts, api_latencies, active_sessions)
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
    run_pipeline()
