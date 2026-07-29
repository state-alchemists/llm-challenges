import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Any

# --- Configuration ---
def get_config() -> Dict[str, str]:
    """Retrieves configuration from environment variables."""
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html"),
    }

# --- Extract ---
def extract_logs(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Reads log file and extracts raw log entries.
    Args:
        log_file_path: Path to the server log file.
    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    log_entries = []
    log_pattern = re.compile(
        r"^(?P<date>\d{4}-\d{2}-\d{2})\s(?P<time>\d{2}:\d{2}:\d{2})\s"
        r"(?P<level>\w+)\s(?P<message>.*)$"
    )
    user_login_pattern = re.compile(r"User (?P<user_id>\w+) logged in")
    user_logout_pattern = re.compile(r"User (?P<user_id>\w+) logged out")
    api_call_pattern = re.compile(r"API (?P<endpoint>/\S+)\s.*took\s(?P<duration>\d+)ms")

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return []

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if match:
                data = match.groupdict()
                full_timestamp = f"{data['date']} {data['time']}"
                level = data['level']
                message = data['message']

                if level == "ERROR":
                    log_entries.append({"dt": full_timestamp, "type": "ERR", "message": message})
                elif level == "INFO":
                    if "User" in message:
                        login_match = user_login_pattern.search(message)
                        logout_match = user_logout_pattern.search(message)
                        if login_match:
                            uid = login_match.group("user_id")
                            log_entries.append({"dt": full_timestamp, "type": "USR", "user_id": uid, "action": "logged in"})
                        elif logout_match:
                            uid = logout_match.group("user_id")
                            log_entries.append({"dt": full_timestamp, "type": "USR", "user_id": uid, "action": "logged out"})
                    elif "API" in message:
                        api_match = api_call_pattern.search(message)
                        if api_match:
                            endpoint = api_match.group("endpoint")
                            duration = int(api_match.group("duration"))
                            log_entries.append({"dt": full_timestamp, "type": "API", "endpoint": endpoint, "duration_ms": duration})
                elif level == "WARN":
                    log_entries.append({"dt": full_timestamp, "type": "WARN", "message": message})
    return log_entries

# --- Transform ---
def transform_data(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transforms raw log entries into structured data for reporting and storage.
    Args:
        log_entries: A list of raw log dictionaries.
    Returns:
        A dictionary containing processed data, including error counts, API latency
        statistics, and active session information.
    """
    error_summary: Dict[str, int] = defaultdict(int)
    api_latency: Dict[str, List[int]] = defaultdict(list)
    active_sessions: Dict[str, str] = {} # user_id -> login_timestamp

    for entry in log_entries:
        if entry["type"] == "ERR":
            error_summary[entry["message"]] += 1
        elif entry["type"] == "API":
            api_latency[entry["endpoint"]].append(entry["duration_ms"])
        elif entry["type"] == "USR":
            user_id = entry["user_id"]
            if entry["action"] == "logged in":
                active_sessions[user_id] = entry["dt"]
            elif entry["action"] == "logged out" and user_id in active_sessions:
                del active_sessions[user_id]
    
    # Calculate average API latency
    avg_api_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_latency.items()
    }

    return {
        "error_summary": dict(error_summary),
        "avg_api_latency": avg_api_latency,
        "active_session_count": len(active_sessions),
    }

# --- Load ---
def load_data(
    config: Dict[str, str],
    transformed_data: Dict[str, Any]
) -> None:
    """
    Loads transformed data into the database and generates the report.
    Args:
        config: Configuration dictionary.
        transformed_data: Dictionary containing processed data.
    """
    db_path = config["DB_PATH"]
    report_file = config["REPORT_FILE"]

    print(f"Connecting to database: {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert error summary
    for msg, count in transformed_data["error_summary"].items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (str(datetime.datetime.now()), msg, count),
        )

    # Insert API metrics
    for ep, avg in transformed_data["avg_api_latency"].items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (str(datetime.datetime.now()), ep, avg),
        )

    conn.commit()
    conn.close()
    print("Data loaded into database.")

    # Generate HTML report
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in transformed_data["error_summary"].items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in transformed_data["avg_api_latency"].items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{transformed_data['active_session_count']} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_file, "w") as f:
        f.write(out)
    print(f"Report generated: {report_file}")


def main():
    """Main function to run the log processing pipeline."""
    config = get_config()
    log_file = config["LOG_FILE"]

    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
        print(f"Created dummy log file: {log_file}")

    # Pipeline execution
    raw_log_entries = extract_logs(log_file)
    transformed_data = transform_data(raw_log_entries)
    load_data(config, transformed_data)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    main()
