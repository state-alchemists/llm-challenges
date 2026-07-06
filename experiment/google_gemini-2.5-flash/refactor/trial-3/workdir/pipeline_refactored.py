import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Optional, Generator, Tuple

def load_config() -> Dict[str, Any]:
    """Loads configuration from environment variables with default fallbacks."""
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "5432")),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html")
    }

LOG_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?:User (?P<user_id>\w+) (?P<user_action>.*)|"
    r"(?:API (?P<endpoint>\S+) took (?P<duration>\d+)ms)|"
    r"(?P<message>.*))$"
)

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parses a single log line using regex and returns a dictionary of its components."""
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None

    data = match.groupdict()
    parsed_entry = {
        "datetime": f"{data['date']} {data['time']}",
        "level": data["level"],
        "raw_message": line.strip()
    }

    if data["level"] == "ERROR" or data["level"] == "WARN":
        parsed_entry["message"] = data["message"].strip() if data["message"] else ""
    elif data["level"] == "INFO":
        if data["user_id"] and data["user_action"]:
            parsed_entry["type"] = "USER_EVENT"
            parsed_entry["user_id"] = data["user_id"]
            parsed_entry["action"] = data["user_action"].strip()
        elif data["endpoint"] and data["duration"]:
            parsed_entry["type"] = "API_CALL"
            parsed_entry["endpoint"] = data["endpoint"]
            parsed_entry["duration"] = int(data["duration"])
    return parsed_entry

def read_log_file(log_file_path: str) -> Generator[Dict[str, Any], None, None]:
    """Reads log file line by line, parses it, and yields parsed entries."""
    if not os.path.exists(log_file_path):
        return
    with open(log_file_path, "r") as f:
        for line in f:
            parsed_line = parse_log_line(line)
            if parsed_line:
                yield parsed_line

def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Establishes and returns a connection to the SQLite database."""
    return sqlite3.connect(db_path)

def initialize_db_tables(cursor: sqlite3.Cursor) -> None:
    """Creates database tables if they do not already exist."""
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

def process_log_entries(
    parsed_entries: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]], Dict[str, str]]:
    """Processes parsed log entries to extract error summary, API latency, and active sessions."""
    error_summary: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in parsed_entries:
        level = entry["level"]
        if level == "ERROR":
            msg = entry["message"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
        elif level == "INFO":
            if entry.get("type") == "USER_EVENT":
                uid = entry["user_id"]
                action = entry["action"]
                if "logged in" in action:
                    active_sessions[uid] = entry["datetime"]
                elif "logged out" in action and uid in active_sessions:
                    active_sessions.pop(uid)
            elif entry.get("type") == "API_CALL":
                endpoint = entry["endpoint"]
                duration = entry["duration"]
                api_latency.setdefault(endpoint, []).append(duration)
        # WARN messages are parsed but not currently processed for DB or report
    return error_summary, api_latency, active_sessions

def insert_error_summary(cursor: sqlite3.Cursor, error_summary: Dict[str, int]) -> None:
    """Inserts error summary data into the database."""
    for msg, count in error_summary.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

def insert_api_metrics(cursor: sqlite3.Cursor, api_latency: Dict[str, List[int]]) -> None:
    """Inserts API latency metrics into the database."""
    for ep, times in api_latency.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )

def generate_html_report(
    error_summary: Dict[str, int],
    api_latency: Dict[str, List[int]],
    active_sessions_count: int
) -> str:
    """Generates the HTML content for the system report."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latency.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

def write_report_file(report_file_path: str, content: str) -> None:
    """Writes the generated HTML content to a file."""
    with open(report_file_path, "w") as f:
        f.write(content)

def main():
    """Main function to orchestrate the log processing and report generation."""
    config = load_config()
    log_file_path = config["LOG_FILE"]
    db_path = config["DB_PATH"]
    report_file_path = config["REPORT_FILE"]

    parsed_entries: List[Dict[str, Any]] = list(read_log_file(log_file_path))

    # Connect to DB and initialize
    print(f"Connecting to {config['DB_HOST']}:{config['DB_PORT']} as {config['DB_USER']}...")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    initialize_db_tables(cursor)

    # Process data (extract, transform)
    error_summary, api_latency, active_sessions = process_log_entries(parsed_entries)

    # Load data into DB
    insert_error_summary(cursor, error_summary)
    insert_api_metrics(cursor, api_latency)

    conn.commit()
    conn.close()

    # Generate and write report
    report_content = generate_html_report(
        error_summary, api_latency, len(active_sessions)
    )
    write_report_file(report_file_path, report_content)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Initial log file creation for demonstration purposes
    config = load_config()
    log_file_path = config["LOG_FILE"]
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()

