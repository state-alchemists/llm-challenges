import datetime
import os
import sqlite3
import re
from typing import Dict, List, Any, Tuple

# Configuration loaded from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost") # Not used for sqlite3, but kept for consistency
DB_PORT = int(os.getenv("DB_PORT", "5432")) # Not used for sqlite3, but kept for consistency
DB_USER = os.getenv("DB_USER", "admin") # Not used for sqlite3, but kept for consistency
DB_PASS = os.getenv("DB_PASS", "password123") # Not used for sqlite3, but kept for consistency

def parse_log_line(line: str) -> Dict[str, Any] | None:
    """
    Parses a single log line using regular expressions.

    Args:
        line: The log line to parse.

    Returns:
        A dictionary containing parsed log data, or None if the line cannot be parsed.
    """
    # Regex for ERROR, INFO (User), INFO (API), and WARN messages
    error_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$")
    info_user_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\w+) (.*)$")
    info_api_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (/[\w/]+) took (\d+)ms$")
    warn_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$")

    if match := error_pattern.match(line):
        return {"d": match.group(1), "t": "ERR", "m": match.group(2).strip()}
    elif match := info_user_pattern.match(line):
        return {"d": match.group(1), "t": "USR", "u": match.group(2), "a": match.group(3).strip()}
    elif match := info_api_pattern.match(line):
        return {"d": match.group(1), "t": "API", "endpoint": match.group(2), "ms": int(match.group(3))}
    elif match := warn_pattern.match(line):
        return {"d": match.group(1), "t": "WARN", "m": match.group(2).strip()}
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts and parses data from the log file.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of parsed log entries.
            - A dictionary of active user sessions (uid -> login_timestamp).
            - A list of API call records.
    """
    parsed_entries: List[Dict[str, Any]] = []
    active_sessions: Dict[str, str] = {}
    api_call_records: List[Dict[str, Any]] = []

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    parsed_entries.append(parsed_line)
                    if parsed_line["t"] == "USR":
                        uid = parsed_line["u"]
                        action = parsed_line["a"]
                        if "logged in" in action:
                            active_sessions[uid] = parsed_line["d"]
                        elif "logged out" in action and uid in active_sessions:
                            active_sessions.pop(uid)
                    elif parsed_line["t"] == "API":
                        api_call_records.append(parsed_line)
    return parsed_entries, active_sessions, api_call_records

def transform_data(
    parsed_entries: List[Dict[str, Any]],
    api_call_records: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms the raw log data into structured metrics.

    Args:
        parsed_entries: A list of parsed log entries.
        api_call_records: A list of API call records.

    Returns:
        A tuple containing:
            - A dictionary of error message counts.
            - A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    error_counts: Dict[str, int] = {}
    for entry in parsed_entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_latencies: Dict[str, List[int]] = {}
    for call in api_call_records:
        ep = call["endpoint"]
        endpoint_latencies.setdefault(ep, []).append(call["ms"])

    return error_counts, endpoint_latencies

def load_metrics_to_db(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]]
) -> None:
    """
    Loads the processed metrics into an SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_counts: A dictionary of error message counts.
        endpoint_latencies: A dictionary mapping API endpoints to a list of their latencies (ms).
    """
    print(f"Connecting to database {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, count)
        )

    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ep, avg)
        )

    conn.commit()
    conn.close()
    print("Metrics loaded to database.")

def generate_html_report(
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_session_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report from the processed metrics.

    Args:
        error_counts: A dictionary of error message counts.
        endpoint_latencies: A dictionary mapping API endpoints to a list of their latencies (ms).
        active_session_count: The number of active user sessions.
        output_file: The name of the output HTML file.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")

def main() -> None:
    """
    Main function to orchestrate the log processing and reporting.
    """
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("""2024-01-01 12:00:00 INFO User 42 logged in
2024-01-01 12:05:00 ERROR Database timeout
2024-01-01 12:05:05 ERROR Database timeout
2024-01-01 12:08:00 INFO API /users/profile took 250ms
2024-01-01 12:09:00 WARN Memory usage at 87%
2024-01-01 12:10:00 INFO User 42 logged out
2024-01-01 12:15:00 INFO User 101 logged in
2024-01-01 12:20:00 INFO API /data/status took 120ms
2024-01-01 12:22:00 ERROR Connection refused
2024-01-01 12:25:00 INFO API /users/profile took 180ms
""")

    parsed_entries, active_sessions, api_call_records = extract_log_data(LOG_FILE)
    error_counts, endpoint_latencies = transform_data(parsed_entries, api_call_records)
    load_metrics_to_db(DB_PATH, error_counts, endpoint_latencies)
    generate_html_report(error_counts, endpoint_latencies, len(active_sessions))

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
