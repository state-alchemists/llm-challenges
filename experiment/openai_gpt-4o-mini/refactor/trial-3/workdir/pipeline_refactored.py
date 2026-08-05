import os
import sqlite3
import datetime
import re
from typing import List, Dict

DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> Dict[str, str]:
    """Parses a single log line and returns a dictionary with extracted data."""
    pattern = r'^(\S+ \S+)\s+(\w+)\s+(.*)$'
    match = re.match(pattern, line)
    if match:
        dt, level, message = match.groups()
        return {'dt': dt, 'level': level, 'message': message.strip()}
    return {}


def process_logs() -> List[Dict[str, str]]:
    """Processes the log file and returns a list of parsed log entries."""
    parsed_logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    parsed_logs.append(parsed_line)
    return parsed_logs


def load_errors_to_db(errors: Dict[str, int]) -> None:
    """Inserts error counts into the database."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        for msg, count in errors.items():
            c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))


def load_api_metrics_to_db(api_metrics: Dict[str, List[int]]) -> None:
    """Inserts API metrics into the database."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        for endpoint, times in api_metrics.items():
            avg = sum(times) / len(times)
            c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), endpoint, avg))


def generate_report(errors: Dict[str, int], api_metrics: Dict[str, List[int]], active_sessions_count: int) -> str:
    """Generates an HTML report from the provided data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    return out


def main() -> None:
    """Main function to process logs and generate report."""
    parsed_log_data = process_logs()

    error_counts = {}
    api_metrics = {}
    active_sessions = {}

    for entry in parsed_log_data:
        if entry['level'] == 'ERROR':
            error_counts[entry['message']] = error_counts.get(entry['message'], 0) + 1
        elif entry['level'] == 'INFO':
            if 'User' in entry['message']:
                parts = entry['message'].split(' ')
                uid = parts[1]
                action = ' '.join(parts[2:])
                if 'logged in' in action:
                    active_sessions[uid] = entry['dt']
                elif 'logged out' in action and uid in active_sessions:
                    active_sessions.pop(uid)
            elif 'API' in entry['message']:
                parts = entry['message'].split(' ')
                endpoint = parts[1]
                duration = int(parts[-1].replace('ms', '').strip())
                api_metrics.setdefault(endpoint, []).append(duration)

    load_errors_to_db(error_counts)
    load_api_metrics_to_db(api_metrics)

    report = generate_report(error_counts, api_metrics, len(active_sessions))

    with open('report.html', 'w') as f:
        f.write(report)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == '__main__':
    main()