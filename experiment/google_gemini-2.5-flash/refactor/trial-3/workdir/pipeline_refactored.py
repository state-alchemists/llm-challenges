
'''
Refactored pipeline script for processing server logs and generating a report.

This script reads server logs, extracts relevant information (errors, API calls,
user sessions), transforms this data into meaningful metrics, loads error and
API latency data into an SQLite database, and generates an HTML report.

Configuration is done via environment variables for security and flexibility.
SQL queries are parameterized to prevent SQL injection vulnerabilities.
Log parsing uses regular expressions for robustness.
'''

import datetime
import os
import sqlite3
import re
from typing import Dict, List, Any, Iterator, Tuple

# --- Configuration --- #
DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")

# Database connection details (for illustration, SQLite does not use these but good practice to include)
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", 5432))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")

# Regex patterns for log parsing
# Corrected LOG_ENTRY_PATTERN to use single curly braces for quantifiers
LOG_ENTRY_PATTERN: re.Pattern = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|WARN|ERROR) "
    r"(?P<raw_message>.*)$"
)

USER_LOGIN_PATTERN: re.Pattern = re.compile(r"User (?P<user_id>\d+) logged in")
USER_LOGOUT_PATTERN: re.Pattern = re.compile(r"User (?P<user_id>\d+) logged out")
API_CALL_PATTERN: re.Pattern = re.compile(r"API /(?P<endpoint>\S+) took (?P<duration>\d+)ms")


# --- Extraction --- #

def extract_log_data(log_file_path: str) -> Iterator[Dict[str, str]]:
    """Reads the log file and yields parsed log entries using regex.

    Args:
        log_file_path: The path to the server log file.

    Yields:
        A dictionary representing a parsed log entry with 'timestamp', 'level', and 'raw_message'.
    """
    if not os.path.exists(log_file_path):
        print(f"Warning: Log file not found at {log_file_path}")
        return

    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_ENTRY_PATTERN.match(line)
            if match:
                yield match.groupdict()
            else:
                print(f"Could not parse log line: {line.strip()}")


# --- Transformation --- #

def transform_log_entries(
    log_entries: Iterator[Dict[str, str]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """Transforms raw log entries into structured data for errors, API calls, and sessions.

    Args:
        log_entries: An iterator of parsed log entry dictionaries.

    Returns:
        A tuple containing:
        - A list of error dictionaries (timestamp, message).
        - A list of API call dictionaries (timestamp, endpoint, duration_ms).
        - A dictionary of active sessions (user_id: login_timestamp).
    """
    errors: List[Dict[str, Any]] = []
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    for entry in log_entries:
        timestamp_str = entry["timestamp"]
        level = entry["level"]
        raw_message = entry["raw_message"]

        if level == "ERROR":
            errors.append({"timestamp": timestamp_str, "message": raw_message.strip()})
        elif level == "INFO":
            # Check for user login/logout events
            login_match = USER_LOGIN_PATTERN.search(raw_message)
            logout_match = USER_LOGOUT_PATTERN.search(raw_message)
            api_match = API_CALL_PATTERN.search(raw_message)

            if login_match:
                user_id = login_match.group("user_id")
                sessions[user_id] = timestamp_str
            elif logout_match:
                user_id = logout_match.group("user_id")
                if user_id in sessions:
                    sessions.pop(user_id)
            elif api_match:
                endpoint = api_match.group("endpoint")
                duration_ms = int(api_match.group("duration"))
                api_calls.append(
                    {"timestamp": timestamp_str, "endpoint": endpoint, "duration_ms": duration_ms}
                )
        # WARN messages are currently just passed through, could be added to errors or a separate category

    return errors, api_calls, sessions


def analyze_errors(errors: List[Dict[str, Any]]) -> Dict[str, int]:
    """Analyzes error entries to count occurrences of each unique error message.

    Args:
        errors: A list of error dictionaries.

    Returns:
        A dictionary where keys are error messages and values are their counts.
    """
    error_summary: Dict[str, int] = {}
    for error in errors:
        msg = error["message"]
        error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary


def analyze_api_latency(
    api_calls: List[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    """Analyzes API call entries to calculate average latency per endpoint.

    Args:
        api_calls: A list of API call dictionaries.

    Returns:
        A dictionary where keys are endpoints and values are dictionaries
        containing 'avg_ms' (average latency in milliseconds).
    """
    endpoint_latencies: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_latencies.setdefault(call["endpoint"], []).append(call["duration_ms"])

    api_latency_summary: Dict[str, Dict[str, float]] = {}
    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        api_latency_summary[ep] = {"avg_ms": avg}
    return api_latency_summary


# --- Loading --- #

def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency_summary: Dict[str, Dict[str, float]],
) -> None:
    """Connects to the database and loads error and API latency summaries.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: Dictionary of error messages and their counts.
        api_latency_summary: Dictionary of API endpoints and their average latencies.
    """
    print(f"Connecting to database: {db_path}")
    # In a real scenario, DB_HOST, DB_PORT, DB_USER, DB_PASS would be used for remote databases.
    # For SQLite, these are illustrative config only.

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert error summary with parameterized query
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    # Insert API latency summary with parameterized query
    for ep, stats in api_latency_summary.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, stats["avg_ms"]),
        )

    conn.commit()
    conn.close()
    print(f"Data loaded to database: {db_path}")


def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_summary: Dict[str, Dict[str, float]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """Generates an HTML report from the processed data.

    Args:
        error_summary: Dictionary of error messages and their counts.
        api_latency_summary: Dictionary of API endpoints and their average latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = '''
<html>
<head><title>System Report</title></head>
<body>
    <h1>Error Summary</h1>
    <ul>
'''
    for err_msg, count in error_summary.items():
        out += f"        <li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "    </ul>\n"

    out += "    <h2>API Latency</h2>\n"
    out += "    <table border='1'>\n"
    out += "        <tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, stats in api_latency_summary.items():
        avg = round(stats["avg_ms"], 1)
        out += f"        <tr><td>{ep}</td><td>{avg}</td></tr>\n"
    out += "    </table>\n"

    out += "    <h2>Active Sessions</h2>\n"
    out += f"    <p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")


def main() -> None:
    """Main function to orchestrate the ETL pipeline.
    """
    print(f"Starting data processing at {datetime.datetime.now()}")

    # Extract
    # Pass LOG_FILE (from environment var) to extract_log_data
    log_entries = extract_log_data(LOG_FILE)

    # Transform
    errors, api_calls, sessions = transform_log_entries(log_entries)
    error_summary = analyze_errors(errors)
    api_latency_summary = analyze_api_latency(api_calls)
    active_sessions_count = len(sessions)

    # Load
    load_to_database(DB_PATH, error_summary, api_latency_summary)
    generate_report_html(error_summary, api_latency_summary, active_sessions_count)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn\'t exist for demonstration
    if not os.path.exists(LOG_FILE):
        print(f"Creating dummy log file: {LOG_FILE}")
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /data/items took 120ms\n")
            f.write("2024-01-01 12:16:00 ERROR Network unreachable\n")

    main()
