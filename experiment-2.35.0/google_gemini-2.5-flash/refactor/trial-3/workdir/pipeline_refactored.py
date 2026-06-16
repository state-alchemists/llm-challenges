import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any

# Load configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")



def parse_log_line(line: str) -> Dict[str, Any] | None:
    """
    Parses a single log line using regex to extract relevant information.

    Args:
        line: The log line string.

    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match the pattern.
    """
    # Regex to capture timestamp, log level, and the rest of the message
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([A-Z]+) (.*)$", line)
    if not match:
        return None

    dt_str, lvl, message = match.groups()

    if lvl == "ERROR":
        return {"d": dt_str, "t": "ERR", "m": message.strip()}
    elif lvl == "INFO" and "User" in message:
        user_match = re.match(r"User (\w+) (.*)", message)
        if user_match:
            uid, action = user_match.groups()
            return {"d": dt_str, "t": "USR", "u": uid, "a": action.strip()}
    elif lvl == "INFO" and "API" in message:
        api_match = re.match(r"API (/\S+)(?: took (\d+)ms)?", message)
        if api_match:
            endpoint, dur_str = api_match.groups()
            duration = int(dur_str) if dur_str else 0
            return {"d": dt_str, "t": "API", "endpoint": endpoint, "ms": duration}
    elif lvl == "WARN":
        return {"d": dt_str, "t": "WARN", "m": message.strip()}
    
    return None

def extract_log_data(log_file: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Reads the log file and parses all lines into a structured format.

    Args:
        log_file: The path to the log file.

    Returns:
        A dictionary containing lists of parsed errors, API calls, and sessions.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return {"errors": [], "api_calls": [], "sessions": {}}

    with open(log_file, "r") as f:
        for line in f:
            parsed_line = parse_log_line(line)
            if parsed_line:
                if parsed_line["t"] == "ERR" or parsed_line["t"] == "WARN":
                    d_list.append(parsed_line)
                elif parsed_line["t"] == "USR":
                    uid = parsed_line["u"]
                    action = parsed_line["a"]
                    dt = parsed_line["d"]
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append(parsed_line)
                elif parsed_line["t"] == "API":
                    api_calls.append(parsed_line)

    return {"errors": d_list, "api_calls": api_calls, "sessions": sessions}


def transform_data(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes extracted log data into error counts, API latency stats, and active sessions.

    Args:
        extracted_data: A dictionary containing lists of parsed errors, API calls, and sessions.

    Returns:
        A dictionary containing processed data: error summary, API latency, and active session count.
    """
    errors_raw = extracted_data["errors"]
    api_calls_raw = extracted_data["api_calls"]
    sessions_raw = extracted_data["sessions"]

    error_summary: Dict[str, int] = {}
    for entry in errors_raw:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    api_latency: Dict[str, List[int]] = {}
    for call in api_calls_raw:
        ep = call["endpoint"]
        api_latency.setdefault(ep, []).append(call["ms"])

    api_avg_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_latency.items()
    }

    active_session_count = len(sessions_raw)

    return {
        "error_summary": error_summary,
        "api_avg_latency": api_avg_latency,
        "active_session_count": active_session_count,
    }

def load_data_to_db(db_path: str, processed_data: Dict[str, Any]) -> None:
    """
    Connects to the database and inserts processed data using parameterized queries.

    Args:
        db_path: The path to the SQLite database file.
        processed_data: A dictionary containing processed data (error summary, API latency).
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert error summary
    for msg, count in processed_data["error_summary"].items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    # Insert API latency metrics
    for ep, avg in processed_data["api_avg_latency"].items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()

def generate_report(processed_data: Dict[str, Any], output_file: str = "report.html") -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        processed_data: A dictionary containing processed data (error summary, API latency, active session count).
        output_file: The name of the output HTML file.
    """
    error_summary = processed_data["error_summary"]
    api_avg_latency = processed_data["api_avg_latency"]
    active_session_count = processed_data["active_session_count"]

    out = """<html>
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
    for ep, avg in api_avg_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_session_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)

def main():
    """
    Main function to orchestrate the log processing and report generation.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    
    extracted_data = extract_log_data(LOG_FILE)
    processed_data = transform_data(extracted_data)
    load_data_to_db(DB_PATH, processed_data)
    generate_report(processed_data)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    # This block generates a sample log file if it doesn't exist.
    # In a production environment, logs would be generated by the server.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()