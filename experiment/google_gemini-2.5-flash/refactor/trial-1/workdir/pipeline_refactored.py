import datetime
import os
import sqlite3

import re
from typing import Dict, List, Any, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex patterns for log parsing
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) "
    r"(?P<message>.*)$"
)
USER_LOGIN_PATTERN = re.compile(r"User (?P<user_id>\w+) logged in")
USER_LOGOUT_PATTERN = re.compile(r"User (?P<user_id>\w+) logged out")
API_CALL_PATTERN = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")


def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts structured data from log file entries.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed log entry.
    """
    parsed_logs = []
    if not os.path.exists(log_file_path):
        logging.warning(f"Log file not found: {log_file_path}")
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_PATTERN.match(line)
            if not match:
                logging.debug(f"Skipping unparseable log line: {line.strip()}")
                continue

            timestamp_str, level, message = match.groups()
            log_entry = {
                "timestamp": timestamp_str,
                "level": level,
                "message": message.strip(),
            }

            if level == "INFO":
                user_login_match = USER_LOGIN_PATTERN.search(message)
                user_logout_match = USER_LOGOUT_PATTERN.search(message)
                api_call_match = API_CALL_PATTERN.search(message)

                if user_login_match:
                    log_entry["type"] = "USER_LOGIN"
                    log_entry["user_id"] = user_login_match.group("user_id")
                elif user_logout_match:
                    log_entry["type"] = "USER_LOGOUT"
                    log_entry["user_id"] = user_logout_match.group("user_id")
                elif api_call_match:
                    log_entry["type"] = "API_CALL"
                    log_entry["endpoint"] = api_call_match.group("endpoint")
                    log_entry["duration_ms"] = int(api_call_match.group("duration"))
                else:
                    log_entry["type"] = "INFO" # Generic INFO
            elif level == "ERROR":
                log_entry["type"] = "ERROR"
            elif level == "WARN":
                log_entry["type"] = "WARN"
            
            parsed_logs.append(log_entry)
    return parsed_logs


def transform_log_data(parsed_logs: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Transforms parsed log data into summarized metrics.

    Args:
        parsed_logs: A list of parsed log entries.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - api_latency: A dictionary mapping API endpoints to a list of their latencies (in ms).
        - active_sessions_count: The number of currently active user sessions.
    """
    error_summary: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {} # user_id -> login_timestamp

    for entry in parsed_logs:
        if entry["type"] == "ERROR":
            error_summary[entry["message"]] = error_summary.get(entry["message"], 0) + 1
        elif entry["type"] == "API_CALL":
            api_latency.setdefault(entry["endpoint"], []).append(entry["duration_ms"])
        elif entry["type"] == "USER_LOGIN":
            sessions[entry["user_id"]] = entry["timestamp"]
        elif entry["type"] == "USER_LOGOUT":
            if entry["user_id"] in sessions:
                sessions.pop(entry["user_id"])
    
    active_sessions_count = len(sessions)
    return error_summary, api_latency, active_sessions_count


def load_to_database(db_path: str, error_summary: Dict[str, int], api_latency: Dict[str, List[int]]) -> None:
    """
    Loads processed data into the SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their latency lists.
    """
    logging.info(f"Connecting to database: {DB_HOST}:{DB_PORT} as {DB_USER}...")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), msg, count),
            )

        for ep, times in api_latency.items():
            avg = sum(times) / len(times) if times else 0.0
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), ep, avg),
            )

        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    finally:
        if conn:
            conn.close()


def generate_html_report(
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their latency lists.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    logging.info(f"Report generated: {output_file}")


def main():
    """
    Main function to orchestrate the log processing and report generation.
    """
    logging.info("Starting log processing job...")
    
    # Extract
    parsed_logs = extract_log_data(LOG_FILE)

    # Transform
    error_summary, api_latency, active_sessions_count = transform_log_data(parsed_logs)

    # Load
    load_to_database(DB_PATH, error_summary, api_latency)
    generate_html_report(error_summary, api_latency, active_sessions_count)

    logging.info(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
