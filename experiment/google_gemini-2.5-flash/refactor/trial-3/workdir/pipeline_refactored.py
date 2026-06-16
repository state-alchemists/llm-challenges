import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex for parsing log lines
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)
USER_LOGIN_PATTERN = re.compile(r".*User (?P<user_id>\w+) logged in")
USER_LOGOUT_PATTERN = re.compile(r".*User (?P<user_id>\w+) logged out")
API_CALL_PATTERN = re.compile(r".*API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")


def _extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts structured data from log file.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing a parsed log entry.
    """
    parsed_entries: List[Dict[str, Any]] = []
    if not os.path.exists(log_file_path):
        return parsed_entries

    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_PATTERN.match(line)
            if match:
                parsed_entries.append(match.groupdict())
    return parsed_entries


def _transform_log_entries(log_entries: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """
    Transforms raw log entries into aggregated error counts, API call latencies, and active sessions.

    Args:
        log_entries: A list of raw log entry dictionaries.

    Returns:
        Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
            - Error message counts.
            - API endpoint latencies.
            - Active user sessions (user_id -> login_timestamp).
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in log_entries:
        level = entry["level"]
        timestamp = entry["timestamp"]
        message = entry["message"]

        if level == "ERROR":
            error_counts[message] = error_counts.get(message, 0) + 1
        elif level == "INFO":
            user_login_match = USER_LOGIN_PATTERN.match(message)
            if user_login_match:
                user_id = user_login_match.group("user_id")
                active_sessions[user_id] = timestamp
            else:
                user_logout_match = USER_LOGOUT_PATTERN.match(message)
                if user_logout_match:
                    user_id = user_logout_match.group("user_id")
                    if user_id in active_sessions:
                        active_sessions.pop(user_id)
                else:
                    api_call_match = API_CALL_PATTERN.match(message)
                    if api_call_match:
                        endpoint = api_call_match.group("endpoint")
                        duration = int(api_call_match.group("duration"))
                        api_latencies.setdefault(endpoint, []).append(duration)
    
    return error_counts, api_latencies, active_sessions


def _load_data_to_db(
    db_path: str,
    db_host: str,
    db_port: int,
    db_user: str,
    db_pass: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """
    Loads processed data into an SQLite database.

    Args:
        db_path: Path to the SQLite database file.
        db_host: Database host (for logging purposes).
        db_port: Database port (for logging purposes).
        db_user: Database user (for logging purposes).
        db_pass: Database password (for logging purposes).
        error_counts: Dictionary of error messages and their counts.
        api_latencies: Dictionary of API endpoints and their latency lists.
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")
    # In a real application, db_pass would not be logged or used directly with sqlite3
    # This is kept for parity with the original script's logging.

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()


def _generate_report(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed log data.

    Args:
        error_counts: Dictionary of error messages and their counts.
        api_latencies: Dictionary of API endpoints and their latency lists.
        active_sessions: Dictionary of active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)


def main_pipeline():
    """
    Main pipeline to process logs, store data, and generate reports.
    """
    log_entries = _extract_log_data(LOG_FILE)
    error_counts, api_latencies, active_sessions = _transform_log_entries(log_entries)

    _load_data_to_db(DB_PATH, DB_HOST, DB_PORT, DB_USER, DB_PASS, error_counts, api_latencies)

    _generate_report(error_counts, api_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main_pipeline()
