import os
import re
import datetime
import sqlite3
from typing import List, Dict, Any


def get_config() -> Dict[str, str]:
    """Fetch configuration from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def parse_log_line(line: str) -> Dict[str, Any]:
    """Parse a log line and return its components."""
    regex = re.compile(r'(?P<datetime>\S+ \S+) (?P<level>\S+) (?P<message>.*)')
    match = regex.match(line)
    if match:
        return match.groupdict() if match else {}
    return {}


def process_server_logs(log_file: str) -> List[Dict[str, Any]]:
    """Process the server log file and extract relevant information."""
    log_entries = []
    with open(log_file, "r") as f:
        for line in f:
            parsed_line = parse_log_line(line)
            if parsed_line:
                log_entries.append(parsed_line)
    return log_entries


def extract_errors(log_entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """Extract error messages and their counts from log entries."""
    error_counts = {}
    for entry in log_entries:
        if entry['level'] == 'ERROR':
            error_counts[entry['message']] = error_counts.get(entry['message'], 0) + 1
    return error_counts


def extract_api_calls(log_entries: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Extract API call metrics from log entries."""
    api_calls = {}
    for entry in log_entries:
        if entry['level'] == 'INFO' and "API" in entry['message']:
            parts = entry['message'].split(" ")
            endpoint = parts[1]  # Assuming it's the second word after 'API'
            api_duration_match = re.search(r'took (\d+)ms', entry['message'])
            duration = int(api_duration_match.group(1)) if api_duration_match else 0
            api_calls.setdefault(endpoint, []).append(duration)
    return api_calls


def store_metrics(db_config: Dict[str, str], error_counts: Dict[str, int], api_calls: Dict[str, List[int]]) -> None:
    """Store error counts and API call metrics in the database."""
    conn = sqlite3.connect(db_config['db_path'])
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    now = datetime.datetime.now().isoformat()
    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

    for ep, durations in api_calls.items():
        avg_duration = sum(durations) / len(durations)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (now, ep, avg_duration))

    conn.commit()
    conn.close()


def generate_report(error_counts: Dict[str, int], api_calls: Dict[str, List[int]], active_sessions: int) -> str:
    """Generate the HTML report from error counts, API calls, and active sessions."""
    report = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    report += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        report += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    report += "</ul>\n"

    report += "<h2>API Latency</h2>\n<table border='1'>\n"
    report += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, durations in api_calls.items():
        avg = sum(durations) / len(durations)
        report += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    report += "</table>\n"

    report += f"<h2>Active Sessions</h2>\n<p>{active_sessions} user(s) currently active</p>\n"
    report += "</body>\n</html>"
    return report


def proc_data():
    config = get_config()
    log_entries = process_server_logs(config['log_file'])
    error_counts = extract_errors(log_entries)
    api_calls = extract_api_calls(log_entries)
    active_sessions = sum(1 for entry in log_entries if entry['level'] == 'INFO' and 'User' in entry['message'])  # Add logic to count sessions

    store_metrics(config, error_counts, api_calls)
    report = generate_report(error_counts, api_calls, active_sessions)

    with open("report.html", "w") as f:
        f.write(report)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    if not os.path.exists(os.getenv("LOG_FILE", "server.log")):
        with open(os.getenv("LOG_FILE", "server.log"), "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()