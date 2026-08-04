import datetime
import os
import re
import sqlite3
from typing import List, Dict, Any, Optional

# --- Configuration ---
# Use environment variables for sensitive or deployment-specific configurations.
# Provide sensible defaults for local development.
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE_PATH", "server.log")
# For a real application, DB_HOST, DB_PORT, DB_USER, DB_PASS would connect to a remote DB.
# For SQLite, these are illustrative and not directly used for connection,
# but kept for consistency with the requirement for credentials via env vars.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123") # In production, use a secret manager, not plaintext in .env

# Regex for parsing log lines
# Captures: timestamp, log level, message parts including user actions, API calls, and errors.
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>[A-Z]+) "
    r"(?P<full_message>.*)$" # General message capturing everything after level
)

def extract_logs(log_file_path: str) -> List[str]:
    """
    Extracts log lines from the specified log file.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of log lines as strings.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found at {log_file_path}. Creating a sample log file.")
        # Create a sample log file if it doesn't exist for demonstration
        with open(log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
        print(f"Sample log file created at {log_file_path}.")

    with open(log_file_path, "r") as f:
        return f.readlines()

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using a regular expression.

    Args:
        line: The log line string to parse.

    Returns:
        A dictionary containing parsed components (timestamp, level, message, etc.)
        or None if the line does not match the expected pattern.
    """
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    data = match.groupdict()
    timestamp = data["timestamp"]
    level = data["level"]
    full_message = data["full_message"].strip()

    parsed_data = {
        "timestamp": timestamp,
        "level": level,
    }

    if level == "INFO":
        user_match = re.search(r"User (\w+) (.*)", full_message)
        api_match = re.search(r"API (/\S+) took (\d+)ms", full_message)
        if user_match:
            parsed_data["type"] = "USR"
            parsed_data["user_id"] = user_match.group(1)
            parsed_data["action"] = user_match.group(2).strip()
        elif api_match:
            parsed_data["type"] = "API"
            parsed_data["endpoint"] = api_match.group(1)
            parsed_data["duration_ms"] = int(api_match.group(2))
        else:
            parsed_data["type"] = "INFO"
            parsed_data["message"] = full_message
    elif level == "ERROR":
        parsed_data["type"] = "ERR"
        parsed_data["message"] = full_message
    elif level == "WARN":
        parsed_data["type"] = "WARN"
        parsed_data["message"] = full_message
    
    return parsed_data

def transform_data(parsed_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transforms a list of parsed log entries into aggregated report data.

    Args:
        parsed_logs: A list of dictionaries, each representing a parsed log line.

    Returns:
        A dictionary containing aggregated data for error summary, API latency,
        and active sessions.
    """
    error_summary: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {} # {user_id: login_timestamp}

    for log_entry in parsed_logs:
        log_type = log_entry.get("type")
        timestamp = log_entry.get("timestamp")

        if log_type == "ERR":
            msg = log_entry.get("message", "Unknown Error")
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif log_type == "API":
            endpoint = log_entry.get("endpoint")
            duration = log_entry.get("duration_ms")
            if endpoint and duration is not None:
                api_latency.setdefault(endpoint, []).append(duration)
        elif log_type == "USR":
            user_id = log_entry.get("user_id")
            action = log_entry.get("action")
            if user_id and isinstance(user_id, str) and action and isinstance(action, str):
                if "logged in" in action:
                    # Ensure timestamp is a string, default to empty string if None
                    active_sessions[user_id] = timestamp if timestamp is not None else ""
                elif "logged out" in action and user_id in active_sessions:
                    active_sessions.pop(user_id)
    
    # Calculate average API latencies
    avg_api_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_latency.items()
    }

    return {
        "error_summary": error_summary,
        "api_latency": avg_api_latency,
        "active_session_count": len(active_sessions),
    }

def load_data_to_db(
    db_path: str,
    db_host: str, # Not directly used for SQLite, but kept for requirement consistency
    db_port: int, # Not directly used for SQLite, but kept for requirement consistency
    db_user: str, # Not directly used for SQLite, but kept for requirement consistency
    db_pass: str, # Not directly used for SQLite, but kept for requirement consistency
    data: Dict[str, Any]
) -> None:
    """
    Loads transformed data into an SQLite database.
    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: The path to the SQLite database file.
        db_host: The database host (illustrative for SQLite).
        db_port: The database port (illustrative for SQLite).
        db_user: The database user (illustrative for SQLite).
        db_pass: The database password (illustrative for SQLite).
        data: A dictionary containing the aggregated data to be loaded.
    """
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create tables if they don't exist
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert error summary
    for msg, count in data["error_summary"].items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

    # Insert API metrics
    for ep, avg in data["api_latency"].items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )

    conn.commit()
    conn.close()
    print(f"Data loaded to {db_path}.")

def generate_report(report_data: Dict[str, Any], output_path: str) -> None:
    """
    Generates an HTML report from the aggregated data.

    Args:
        report_data: A dictionary containing the aggregated data for the report.
        output_path: The path where the HTML report will be saved.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in report_data["error_summary"].items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += """<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, avg in report_data["api_latency"].items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += """<h2>Active Sessions</h2>
<p>""" + str(report_data["active_session_count"]) + """ user(s) currently active</p>\n"""
    out += "</body>\n</html>"

    with open(output_path, "w") as f:
        f.write(out)
    print(f"Report generated at {output_path}.")

def main():
    """
    Main function to orchestrate the log processing pipeline.
    """
    print(f"Starting log processing job at {datetime.datetime.now()}")

    log_lines = extract_logs(LOG_FILE)
    parsed_logs = [parse_log_line(line) for line in log_lines]
    # Filter out None values from parsing errors
    parsed_logs = [log for log in parsed_logs if log is not None]

    transformed_data = transform_data(parsed_logs)

    load_data_to_db(DB_PATH, DB_HOST, DB_PORT, DB_USER, DB_PASS, transformed_data)
    generate_report(transformed_data, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
