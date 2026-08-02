import datetime
import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple, Any

# --- Configuration Loading ---

def load_config() -> Dict[str, str]:
    """Loads configuration from environment variables."""
    config = {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
    }
    return config

# --- Extract Phase ---

def extract_logs(log_file_path: str) -> List[str]:
    """
    Extracts log lines from the specified log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of raw log lines.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return []
    with open(log_file_path, "r") as f:
        return f.readlines()

# --- Transform Phase ---

# Regex pattern for log parsing
# Group 1: timestamp (YYYY-MM-DD HH:MM:SS)
# Group 2: log level (INFO|ERROR|WARN)
# Group 3: message content
LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$")
USER_LOG_PATTERN = re.compile(r"User (\w+) (.*)$")
API_LOG_PATTERN = re.compile(r"API (/[\w/]+) took (\d+)ms$")

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex.

    Args:
        line: A single log line string.

    Returns:
        A dictionary containing parsed log data (timestamp, level, message, etc.)
        or None if the line cannot be parsed.
    """
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    timestamp_str, level, message = match.groups()
    log_entry: Dict[str, Any] = {"timestamp": timestamp_str, "level": level, "message": message.strip()}

    if level == "INFO":
        user_match = USER_LOG_PATTERN.search(message)
        api_match = API_LOG_PATTERN.search(message)

        if user_match:
            log_entry["type"] = "USR"
            log_entry["user_id"], log_entry["action"] = user_match.groups()
        elif api_match:
            log_entry["type"] = "API"
            log_entry["endpoint"], latency_ms = api_match.groups()
            log_entry["latency_ms"] = int(latency_ms)
        else:
            log_entry["type"] = "INFO_GENERIC" # Generic info, if not user or API
    elif level == "ERROR":
        log_entry["type"] = "ERR"
    elif level == "WARN":
        log_entry["type"] = "WARN"
    else:
        log_entry["type"] = "UNKNOWN"

    return log_entry

def transform_logs(log_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Transforms raw log lines into structured dictionaries.

    Args:
        log_lines: A list of raw log lines.

    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    parsed_logs = []
    for line in log_lines:
        entry = parse_log_line(line)
        if entry:
            parsed_logs.append(entry)
    return parsed_logs

def analyze_data(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes parsed log entries to generate reports.

    Args:
        log_entries: A list of dictionaries, each a parsed log entry.

    Returns:
        A dictionary containing the analysis results: error summary, API latency,
        and active sessions count.
    """
    error_summary: Dict[str, int] = {}
    api_call_latencies: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {} # user_id: login_timestamp

    for entry in log_entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif entry["type"] == "USR":
            user_id = entry["user_id"]
            action = entry["action"]
            if "logged in" in action:
                active_sessions[user_id] = entry["timestamp"]
            elif "logged out" in action and user_id in active_sessions:
                active_sessions.pop(user_id)
        elif entry["type"] == "API":
            endpoint = entry["endpoint"]
            latency = entry["latency_ms"]
            api_call_latencies.setdefault(endpoint, []).append(latency)

    # Calculate average API latencies
    api_latency_report: List[Tuple[str, float]] = []
    for ep, latencies in api_call_latencies.items():
        avg = sum(latencies) / len(latencies) if latencies else 0.0
        api_latency_report.append((ep, avg))

    return {
        "error_summary": error_summary,
        "api_latency_report": api_latency_report,
        "active_sessions_count": len(active_sessions),
    }


# --- Load Phase ---

def create_db_schema(db_path: str) -> None:
    """
    Creates necessary tables in the SQLite database if they don't exist.

    Args:
        db_path: The path to the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    conn.close()

def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    api_latency_report: List[Tuple[str, float]],
) -> None:
    """
    Loads processed data into the SQLite database.

    Args:
        db_path: The path to the SQLite database.
        error_summary: A dictionary summarizing error messages and their counts.
        api_latency_report: A list of tuples with API endpoint and average latency.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Insert errors (using parameterized query)
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (str(datetime.datetime.now()), msg, count),
        )

    # Insert API metrics (using parameterized query)
    for ep, avg in api_latency_report:
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (str(datetime.datetime.now()), ep, avg),
        )
    conn.commit()
    conn.close()

def generate_report_html(
    error_summary: Dict[str, int],
    api_latency_report: List[Tuple[str, float]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the analyzed data.

    Args:
        error_summary: A dictionary summarizing error messages and their counts.
        api_latency_report: A list of tuples with API endpoint and average latency.
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
    for ep, avg in api_latency_report:
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

# --- Main Logic ---

def main():
    """Main function to run the log processing pipeline."""
    config = load_config()
    db_path = config["DB_PATH"]
    log_file_path = config["LOG_FILE"]
    # DB_HOST, DB_PORT, DB_USER, DB_PASS are loaded but not used in this sqlite-only script,
    # but kept for completeness per requirement 1 (env vars for all config).

    print(f"Starting log processing job at {datetime.datetime.now()}")
    # These print statements are kept for informational purposes as in original script.
    print(f"Using DB_PATH: {db_path}, LOG_FILE: {log_file_path}")
    print(f"Connecting to {config['DB_HOST']}:{config['DB_PORT']} as {config['DB_USER']}...")

    # Ensure DB schema exists
    create_db_schema(db_path)

    # Extract
    log_lines = extract_logs(log_file_path)

    # Transform
    parsed_log_entries = transform_logs(log_lines)
    analysis_results = analyze_data(parsed_log_entries)

    # Load
    load_data_to_db(
        db_path,
        analysis_results["error_summary"],
        analysis_results["api_latency_report"],
    )
    generate_report_html(
        analysis_results["error_summary"],
        analysis_results["api_latency_report"],
        analysis_results["active_sessions_count"],
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # This part remains for testing purposes, creating a dummy log file if it doesn't exist.
    log_file_for_init = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_file_for_init):
        with open(log_file_for_init, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /data/items took 120ms\n")
            f.write("2024-01-01 12:20:00 ERROR Connection reset\n")
    main()
