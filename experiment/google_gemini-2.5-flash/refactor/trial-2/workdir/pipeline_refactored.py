import os
import re
import sqlite3
import datetime
from typing import List, Dict, Tuple, Any

class Config:
    """
    Configuration class to load settings from environment variables.
    Provides default values if environment variables are not set.
    """
    DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
    LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
    # DB_HOST, DB_PORT, DB_USER, DB_PASS are not strictly used by sqlite3,
    # but kept for completeness as per requirement 1.
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "admin")
    DB_PASS: str = os.getenv("DB_PASS", "password123")
    REPORT_FILE: str = os.getenv("REPORT_FILE", "report.html")

# Regex pattern to capture timestamp, log level, and the rest of the message
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "  # Timestamp (e.g., 2024-01-01 12:00:00)
    r"(INFO|ERROR|WARN) "                      # Log Level (INFO, ERROR, WARN)
    r"(.*)$"                                   # Message content
)

# Regex patterns for specific message types
USER_ACTION_PATTERN = re.compile(r"User (\w+) (.*)")
API_CALL_PATTERN = re.compile(r"API (/[\w/]+) took (\d+)ms")

def extract_logs(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts and initially parses log entries from the specified log file using regex.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, each representing a parsed log entry with
        'timestamp' (datetime), 'level' (str), and 'message' (str).
    """
    log_entries: List[Dict[str, Any]] = []
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return log_entries

    print(f"Extracting logs from {log_file_path}...")
    with open(log_file_path, "r") as f:
        for line in f:
            match = LOG_LINE_PATTERN.match(line)
            if match:
                timestamp_str, level, message = match.groups()
                try:
                    timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    log_entries.append({
                        "timestamp": timestamp,
                        "level": level,
                        "message": message.strip()
                    })
                except ValueError:
                    print(f"Warning: Could not parse timestamp in line: {line.strip()}")
            else:
                print(f"Warning: Line did not match expected log pattern: {line.strip()}")
    print(f"Extracted {len(log_entries)} log entries.")
    return log_entries

def transform_log_entries(log_entries: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """
    Transforms raw log entries into aggregated data for reporting and database storage.

    Args:
        log_entries: A list of parsed log entry dictionaries.

    Returns:
        A tuple containing:
        - error_summary: Dictionary mapping error messages to their counts.
        - api_latency_stats: Dictionary mapping API endpoints to a list of latencies (ms).
        - active_session_count: The number of currently active user sessions.
    """
    print("Transforming log entries...")
    error_summary: Dict[str, int] = {}
    api_latency_stats: Dict[str, List[int]] = {}
    sessions: Dict[str, datetime.datetime] = {} # Tracks currently logged-in users

    for entry in log_entries:
        level = entry["level"]
        message = entry["message"]
        # timestamp = entry["timestamp"] # Not used directly in transformation logic for this report

        if level == "ERROR":
            error_summary[message] = error_summary.get(message, 0) + 1
        elif level == "INFO":
            # Check for User actions
            user_match = USER_ACTION_PATTERN.search(message)
            if user_match:
                uid, action = user_match.groups()
                if "logged in" in action:
                    sessions[uid] = entry["timestamp"] # Store login time
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
            
            # Check for API calls
            api_match = API_CALL_PATTERN.search(message)
            if api_match:
                endpoint, duration_str = api_match.groups()
                try:
                    duration_ms = int(duration_str)
                    api_latency_stats.setdefault(endpoint, []).append(duration_ms)
                except ValueError:
                    print(f"Warning: Could not parse API duration in message: {message}")
    
    active_session_count = len(sessions)
    print("Transformation complete.")
    return error_summary, api_latency_stats, active_session_count

def load_to_database(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]]
) -> None:
    """
    Loads processed error and API metrics data into an SQLite database.
    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: Dictionary mapping error messages to their counts.
        api_latency_stats: Dictionary mapping API endpoints to a list of latencies (ms).
    """
    conn = None
    print(f"Connecting to database: {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        # Insert error summary data using parameterized query
        for msg, count in error_summary.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (datetime.datetime.now().isoformat(), msg, count)
            )

        # Insert API metrics data using parameterized query
        for ep, times in api_latency_stats.items():
            if times: # Only insert if there are recorded times for the endpoint
                avg = sum(times) / len(times)
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (datetime.datetime.now().isoformat(), ep, avg)
                )

        conn.commit()
        print("Data loaded to database.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
    active_session_count: int,
    output_file: str
) -> None:
    """
    Generates an HTML report from the processed log data.

    Args:
        error_summary: Dictionary mapping error messages to their counts.
        api_latency_stats: Dictionary mapping API endpoints to a list of latencies (ms).
        active_session_count: The number of currently active user sessions.
        output_file: The path where the generated HTML report will be saved.
    """
    print(f"Generating HTML report to {output_file}...")
    out = "<!DOCTYPE html>\n<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    if not error_summary:
        out += "<li>No errors recorded.</li>\n"
    else:
        for err_msg, count in error_summary.items():
            out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    if not api_latency_stats:
        out += "<tr><td colspan='2'>No API calls recorded.</td></tr>\n"
    else:
        for ep, times in api_latency_stats.items():
            if times:
                avg = sum(times) / len(times)
                out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    try:
        with open(output_file, "w") as f:
            f.write(out)
        print(f"Report generated successfully to {output_file}")
    except IOError as e:
        print(f"Error writing report to {output_file}: {e}")

def main():
    """
    Main function to orchestrate the log processing pipeline: Extract -> Transform -> Load.
    """
    config = Config()
    
    print(f"Starting log processing job at {datetime.datetime.now()}")

    # Extract
    log_entries = extract_logs(config.LOG_FILE)

    # Transform
    error_summary, api_latency_stats, active_session_count = transform_log_entries(log_entries)

    # Load (Database)
    load_to_database(config.DB_PATH, error_summary, api_latency_stats)

    # Load (Report)
    generate_report_html(error_summary, api_latency_stats, active_session_count, config.REPORT_FILE)

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for testing purposes
    # This block is for initial setup/demonstration and can be removed in production
    if not os.path.exists(Config.LOG_FILE):
        print(f"Creating dummy log file: {Config.LOG_FILE}")
        with open(Config.LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO User 100 logged in\n")
            f.write("2024-01-01 12:20:00 INFO API /products/list took 100ms\n")
            f.write("2024-01-01 12:21:00 INFO API /products/list took 150ms\n")
            f.write("2024-01-01 12:25:00 ERROR Connection refused\n")
            f.write("2024-01-01 12:30:00 INFO User 200 logged in\n")
            f.write("2024-01-01 12:35:00 INFO User 100 logged out\n") # User 100 logs out
    
    main()
