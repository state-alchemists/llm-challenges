import datetime
import sqlite3
import re
import os
from typing import Dict, List, Any

# 1. Use environment variables for all config
DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")


def get_db_connection() -> sqlite3.Connection:
    """Establishes and returns a connection to the SQLite database."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(DB_PATH)
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Creates necessary tables in the SQLite database if they don't exist."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()


def extract_logs(log_file_path: str) -> List[Dict[str, Any]]:
    """Extracts structured data from log file lines using regex.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    parsed_logs: List[Dict[str, Any]] = []
    # 4. Use regex for log line parsing
    log_pattern = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"  # Timestamp
        r"(?P<level>INFO|ERROR|WARN)\s+"  # Log Level
        r"(?:User\s+(?P<user_id>\w+)\s+(?P<user_action>.*)|"  # User activity
        r"API\s+(?P<api_endpoint>/\S+)(?:\s+took\s+(?P<api_duration>\d+)ms)?|"  # API call
        r"(?P<message>.*))"  # Generic message for ERROR/WARN
    )

    if not os.path.exists(log_file_path):
        print(f"Log file not found at {log_file_path}")
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if match:
                data = match.groupdict()
                parsed_logs.append(data)
            else:
                print(f"Skipping unparseable log line: {line.strip()}")
    return parsed_logs


def transform_data(parsed_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transforms raw parsed log data into structured metrics.

    Args:
        parsed_logs: A list of parsed log entries.

    Returns:
        A dictionary containing transformed data for errors, API calls, and sessions.
    """
    error_summary: Dict[str, int] = {}
    api_latency_data: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for log in parsed_logs:
        log_level = log.get("level")
        if log_level == "ERROR":
            message = log.get("message")
            if message:
                error_summary[message.strip()] = error_summary.get(message.strip(), 0) + 1
        elif log_level == "INFO":
            if log.get("user_id") and log.get("user_action"):
                user_id = log["user_id"]
                action = log["user_action"]
                timestamp = log["timestamp"]
                if "logged in" in action:
                    active_sessions[user_id] = timestamp
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
            elif log.get("api_endpoint") and log.get("api_duration"):
                endpoint = log["api_endpoint"]
                duration = int(log["api_duration"]) if log["api_duration"] else 0
                api_latency_data.setdefault(endpoint, []).append(duration)

    return {
        "error_summary": error_summary,
        "api_latency_data": api_latency_data,
        "active_sessions_count": len(active_sessions),
    }


def load_data_to_db(
    conn: sqlite3.Connection,
    error_summary: Dict[str, int],
    api_latency_data: Dict[str, List[int]],
) -> None:
    """Loads transformed data into the SQLite database.

    Args:
        conn: The database connection object.
        error_summary: Dictionary of error messages and their counts.
        api_latency_data: Dictionary of API endpoints and their latencies.
    """
    cursor = conn.cursor()

    # 2. Fix the SQL injection - use parameterized queries
    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, count),
        )

    for ep, times in api_latency_data.items():
        avg = sum(times) / len(times) if times else 0.0
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ep, avg),
        )
    conn.commit()


def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_data: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """Generates an HTML report from the processed data.

    Args:
        error_summary: Dictionary of error messages and their counts.
        api_latency_data: Dictionary of API endpoints and their latencies.
        active_sessions_count: The number of active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = f"""
<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency_data.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

    print(f"Report generated at {output_file}")


def main():
    """Main function to run the log processing and reporting pipeline."""
    conn = get_db_connection()
    create_tables(conn)

    parsed_logs = extract_logs(LOG_FILE)
    transformed_data = transform_data(parsed_logs)

    load_data_to_db(
        conn,
        transformed_data["error_summary"],
        transformed_data["api_latency_data"],
    )

    generate_report_html(
        transformed_data["error_summary"],
        transformed_data["api_latency_data"],
        transformed_data["active_sessions_count"],
    )

    conn.close()
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # For demonstration, create a dummy log file if it doesn't exist
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
