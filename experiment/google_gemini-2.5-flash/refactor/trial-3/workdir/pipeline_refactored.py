import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple

@dataclass
class Config:
    """
    Configuration settings for the log processing pipeline.
    Loaded from environment variables.
    """
    db_path: str
    log_file_path: str
    report_file_path: str
    db_host: str
    db_port: int
    db_user: str
    db_password: str

def load_config() -> Config:
    """
    Loads configuration from environment variables.
    Provides default values if environment variables are not set.
    """
    return Config(
        db_path=os.getenv("DB_PATH", "metrics.db"),
        log_file_path=os.getenv("LOG_FILE_PATH", "server.log"),
        report_file_path=os.getenv("REPORT_FILE_PATH", "report.html"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_user=os.getenv("DB_USER", "admin"),
        db_password=os.getenv("DB_PASSWORD", "password123"),
    )

def parse_log_line(line: str) -> Dict[str, Any] | None:
    """
    Parses a single log line using regular expressions.

    Args:
        line: The log line string to parse.

    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match a known pattern.
    """
    # Example log patterns:
    # 2024-01-01 12:00:00 INFO User 42 logged in
    # 2024-01-01 12:05:00 ERROR Database timeout
    # 2024-01-01 12:08:00 INFO API /users/profile took 250ms
    # 2024-01-01 12:09:00 WARN Memory usage at 87%

    # Timestamp pattern
    ts_pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"

    # ERROR pattern
    error_match = re.match(rf"^{ts_pattern} ERROR (.*)", line)
    if error_match:
        return {"timestamp": error_match.group(1), "type": "ERROR", "message": error_match.group(2).strip()}

    # INFO User pattern
    user_info_match = re.match(rf"^{ts_pattern} INFO User (\d+) (.*)", line)
    if user_info_match:
        return {"timestamp": user_info_match.group(1), "type": "USER_ACTION", "user_id": user_info_match.group(2), "action": user_info_match.group(3).strip()}

    # INFO API pattern
    api_info_match = re.match(rf"^{ts_pattern} INFO API (/\\S+) took (\d+)ms", line)
    if api_info_match:
        return {"timestamp": api_info_match.group(1), "type": "API_CALL", "endpoint": api_info_match.group(2), "duration_ms": int(api_info_match.group(3))}

    # WARN pattern
    warn_match = re.match(rf"^{ts_pattern} WARN (.*)", line)
    if warn_match:
        return {"timestamp": warn_match.group(1), "type": "WARN", "message": warn_match.group(2).strip()}

    return None

def extract_log_data(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Extracts structured data from the log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed log entry.
    """
    parsed_entries: List[Dict[str, Any]] = []
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    parsed_entries.append(parsed_line)
    return parsed_entries

def transform_log_data(
    parsed_entries: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """
    Transforms the parsed log entries into a summarized format for reporting.

    Args:
        parsed_entries: A list of dictionaries with parsed log entries.

    Returns:
        A tuple containing:
        - error_summary: A dictionary mapping error messages to their counts.
        - api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
        - active_sessions: A dictionary mapping active user IDs to their login timestamps.
    """
    error_summary: Dict[str, int] = {}
    api_latency_stats: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in parsed_entries:
        if entry["type"] == "ERROR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif entry["type"] == "USER_ACTION":
            user_id = entry["user_id"]
            action = entry["action"]
            if "logged in" in action:
                active_sessions[user_id] = entry["timestamp"]
            elif "logged out" in action and user_id in active_sessions:
                active_sessions.pop(user_id)
        elif entry["type"] == "API_CALL":
            endpoint = entry["endpoint"]
            duration = entry["duration_ms"]
            api_latency_stats.setdefault(endpoint, []).append(duration)

    return error_summary, api_latency_stats, active_sessions

def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database and creates necessary tables.

    Args:
        db_path: The path to the SQLite database file.

    Returns:
        A SQLite database connection object.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn

def load_data_to_db(
    conn: sqlite3.Connection,
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
) -> None:
    """
    Loads the transformed data into the SQLite database.

    Args:
        conn: The SQLite database connection object.
        error_summary: A dictionary mapping error messages to their counts.
        api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    c = conn.cursor()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (current_time, msg, count),
        )

    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times) if times else 0
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (current_time, ep, avg),
        )
    conn.commit()

def generate_html_report(
    config: Config,
    error_summary: Dict[str, int],
    api_latency_stats: Dict[str, List[int]],
    active_sessions_count: int,
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        config: The configuration object containing report file path.
        error_summary: A dictionary mapping error messages to their counts.
        api_latency_stats: A dictionary mapping API endpoints to a list of their latencies (ms).
        active_sessions_count: The number of currently active user sessions.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\\n"
    out += "</ul>\\n"

    out += """<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, times in api_latency_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\\n"
    out += "</table>\\n"

    out += f"""<h2>Active Sessions</h2>
<p>{active_sessions_count} user(s) currently active</p>
</body>
</html>"""

    with open(config.report_file_path, "w") as f:
        f.write(out)

def main() -> None:
    """
    Main function to orchestrate the log processing and reporting pipeline.
    """
    config = load_config()

    print(f"Processing logs from {config.log_file_path}...")
    parsed_entries = extract_log_data(config.log_file_path)

    error_summary, api_latency_stats, active_sessions = transform_log_data(parsed_entries)

    print(f"Connecting to database {config.db_path}...")
    conn = initialize_database(config.db_path)
    try:
        load_data_to_db(conn, error_summary, api_latency_stats)
    finally:
        conn.close()
    print("Data loaded to database.")

    print(f"Generating HTML report at {config.report_file_path}...")
    generate_html_report(config, error_summary, api_latency_stats, len(active_sessions))
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    # In a real scenario, this log file would be generated by a server
    config = load_config()
    if not os.path.exists(config.log_file_path):
        with open(config.log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\\n")
            f.write("2024-01-01 12:05:05 ERROR Another database error occurred\\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\\n")
            f.write("2024-01-01 12:11:00 INFO API /data/items took 120ms\\n")
            f.write("2024-01-01 12:12:00 INFO User 101 logged in\\n")
    main()
