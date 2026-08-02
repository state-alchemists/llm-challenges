import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

# Configuration from environment variables
DATABASE_PATH = os.getenv("DATABASE_PATH", "metrics.db")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "server.log")
# These are defined for completeness but not used by sqlite3
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>(INFO|ERROR|WARN)) "
    r"(?P<message>.*)$"
)
INFO_USER_PATTERN = re.compile(r"User (?P<user_id>\w+) (?P<action>.*)")
INFO_API_PATTERN = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")


def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts and parses log data from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    parsed_logs = []
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_LINE_PATTERN.match(line)
            if match:
                data = match.groupdict()
                parsed_logs.append(data)
            else:
                print(f"Skipping unparseable log line: {line.strip()}")
    return parsed_logs


def transform_log_data(
    parsed_logs: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """
    Transforms parsed log data into structured metrics for reporting.

    Args:
        parsed_logs: A list of dictionaries, each a parsed log entry.

    Returns:
        A tuple containing:
        - A dictionary of error messages and their counts.
        - A dictionary of API endpoints and a list of their latencies (ms).
        - A dictionary of active user sessions (user_id to login timestamp).
    """
    error_counts: Dict[str, int] = {}
    api_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {} # user_id -> login_timestamp

    for entry in parsed_logs:
        level = entry["level"]
        message = entry["message"]
        timestamp = entry["timestamp"]

        if level == "ERROR":
            error_counts[message] = error_counts.get(message, 0) + 1
        elif level == "INFO":
            user_match = INFO_USER_PATTERN.match(message)
            api_match = INFO_API_PATTERN.match(message)

            if user_match:
                uid = user_match["user_id"]
                action = user_match["action"]
                if "logged in" in action:
                    active_sessions[uid] = timestamp
                elif "logged out" in action and uid in active_sessions:
                    active_sessions.pop(uid)
            elif api_match:
                endpoint = api_match["endpoint"]
                duration = int(api_match["duration"])
                api_latencies.setdefault(endpoint, []).append(duration)
        # WARN messages are currently processed only for the HTML report
        # but not stored in DB, keeping logic consistent with original script.

    return error_counts, api_latencies, active_sessions


def load_data_to_db(
    database_path: str,
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
) -> None:
    """
    Loads error counts and API latency metrics into an SQLite database.

    Args:
        database_path: The path to the SQLite database file.
        error_counts: A dictionary of error messages and their counts.
        api_latencies: A dictionary of API endpoints and their latencies.
    """
    conn = sqlite3.connect(database_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    # Insert error counts using parameterized queries
    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    # Insert API metrics using parameterized queries
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), ep, avg),
            )

    conn.commit()
    conn.close()
    print(f"Data loaded into database: {database_path}")


def generate_report_html(
    error_counts: Dict[str, int],
    api_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed log data.

    Args:
        error_counts: A dictionary of error messages and their counts.
        api_latencies: A dictionary of API endpoints and their latencies.
        active_sessions: A dictionary of active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>"
    out += "</ul>\n"

    out += """<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in api_latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>"
    out += "</table>\n"

    out += """<h2>Active Sessions</h2>
"""
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += """</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")


def main():
    """
    Main function to orchestrate the log processing pipeline.
    """
    print(f"Starting log processing at {datetime.datetime.now()}")
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} (using {DATABASE_PATH} for SQLite)...")

    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO User 10 logged in\n")


    parsed_logs = extract_log_data(LOG_FILE_PATH)
    error_counts, api_latencies, active_sessions = transform_log_data(parsed_logs)
    load_data_to_db(DATABASE_PATH, error_counts, api_latencies)
    generate_report_html(error_counts, api_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
