import datetime
import os
import re
import sqlite3
from typing import List, Dict, Any

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_file(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Parses the server log file using regular expressions to extract structured data.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A list of dictionaries, where each dictionary represents a parsed log entry.
    """
    parsed_logs: List[Dict[str, Any]] = []
    log_pattern = re.compile(
        r"""^(?P<timestamp>\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) """
        r"""(?P<level>\w+) """
        r"""(?:User (?P<user_id>\d+) (?P<user_action>.*)|"""
        r"""API (?P<api_endpoint>\S+)(?: took (?P<api_duration>\d+)ms)?|"""
        r"""(?P<message>.*))$"""
    )

    if not os.path.exists(log_file_path):
        return parsed_logs

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if match:
                data = match.groupdict()
                parsed_logs.append(data)
    return parsed_logs


def analyze_data(parsed_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes parsed log data to extract error summaries, API call statistics,
    and active user sessions.

    Args:
        parsed_logs: A list of dictionaries, each representing a parsed log entry.

    Returns:
        A dictionary containing 'error_summary', 'api_latency', and 'active_sessions'.
    """
    error_summary: Dict[str, int] = {}
    api_calls: Dict[str, List[int]] = {}
    sessions: Dict[str, str] = {}

    for entry in parsed_logs:
        timestamp = entry.get("timestamp", "")
        level = entry.get("level")

        if level == "ERROR":
            message = entry.get("message")
            if message:
                error_summary[message] = error_summary.get(message, 0) + 1
        elif level == "INFO":
            if entry.get("user_id"):
                user_id = entry["user_id"]
                user_action = entry["user_action"]
                if "logged in" in user_action:
                    sessions[user_id] = timestamp
                elif "logged out" in user_action and user_id in sessions:
                    sessions.pop(user_id)
            elif entry.get("api_endpoint"):
                endpoint = entry["api_endpoint"]
                duration_str = entry.get("api_duration", "0")
                duration = int(duration_str) if duration_str else 0
                api_calls.setdefault(endpoint, []).append(duration)

    api_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_calls.items()
    }

    return {
        "error_summary": error_summary,
        "api_latency": api_latency,
        "active_sessions": len(sessions),
    }


def store_data_in_db(
    db_path: str, error_summary: Dict[str, int], api_latency: Dict[str, float]
) -> None:
    """
    Stores the analyzed error summary and API latency data into an SQLite database.
    Uses parameterized queries to prevent SQL injection.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their average latencies.
    """
    print("Connecting to " + DB_HOST + ":" + str(DB_PORT) + " as " + DB_USER + "...")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Store error summary
    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    # Store API latency
    for ep, avg in api_latency.items():
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report_html(
    error_summary: Dict[str, int],
    api_latency: Dict[str, float],
    active_sessions: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the analyzed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_latency: A dictionary of API endpoints and their average latencies.
        active_sessions: The count of currently active user sessions.
        output_file: The path to the output HTML file.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print("Job finished at " + str(datetime.datetime.now()))


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

    parsed_logs = parse_log_file(LOG_FILE)
    analysis_results = analyze_data(parsed_logs)
    store_data_in_db(DB_PATH, analysis_results["error_summary"], analysis_results["api_latency"])
    generate_report_html(
        analysis_results["error_summary"],
        analysis_results["api_latency"],
        analysis_results["active_sessions"],
    )
