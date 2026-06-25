import os
import re
import sqlite3
import datetime
from typing import List, Dict, Optional, Tuple

# Environment configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Optional[Dict[str, str]]:
    """Parse a single log line and return structured data."""
    log_pattern = re.compile(r'^(\S+ \S+) (\w+) (.*)$')
    match = log_pattern.match(line)
    if not match:
        return None
    dt, lvl, message = match.groups()
    return {'dt': dt, 'level': lvl, 'message': message}


def process_log_file(log_file: str) -> List[Dict[str, str]]:
    """Process the log file and return a list of structured log messages."""
    data_list = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line.strip())
                if parsed_line:
                    data_list.append(parsed_line)
    return data_list


def transform_log_data(raw_logs: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, int]]]:
    """Transform raw log data into separate categories for errors, user actions, and API calls."""
    d_list = []
    sessions = {}  # type: Dict[str, str]
    api_calls: List[Dict[str, int]] = []  # Initialize api_calls as a list of dicts

    for entry in raw_logs:
        dt = entry['dt']
        lvl = entry['level']
        message = entry['message']
        if lvl == "ERROR":
            d_list.append({"d": dt, "t": "ERR", "m": message})
        elif lvl == "INFO":
            if "User" in message:
                uid = re.search(r'User (\d+)', message)
                if uid:
                    uid = uid.group(1)
                    action = message.split(f"User {uid} ")[1].strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
            elif "API" in message:
                endpoint = re.search(r'API (\S+)', message)
                dur = re.search(r'took (\d+)ms', message)
                if endpoint and dur:
                    api_calls.append({"d": dt, "endpoint": endpoint.group(1), "ms": int(dur.group(1))})
        elif lvl == "WARN":
            d_list.append({"d": dt, "t": "WARN", "m": message})
    return d_list, sessions, api_calls


def load_data_to_db(error_data: List[Dict[str, str]], api_call_data: List[Dict[str, int]]) -> None:
    """Load transformed data into the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}  # type: Dict[str, int]
    for error in error_data:
        msg = error["m"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}  # type: Dict[str, List[int]]
    for call in api_call_data:
        ep = call["endpoint"]
        if ep not in endpoint_stats:
            endpoint_stats[ep] = []
        endpoint_stats[ep].append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(t for t in times if t is not None) / (len(times) if len(times) > 0 else 1)  # Prevent division by zero
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(error_data: List[Dict[str, str]], api_call_data: List[Dict[str, int]], active_sessions: Dict[str, str]) -> str:
    """Generate an HTML report based on processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {}  # Initialize empty error_counts for report use
    for error in error_data:
        msg = error["m"]
        count = error_counts.get(msg, 0)
        out += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}  # Store API latency stats
    for call in api_call_data:
        ep = call["endpoint"]
        if ep not in endpoint_stats:
            endpoint_stats[ep] = []
        endpoint_stats[ep].append(call["ms"])
    for ep, times in endpoint_stats.items():
        avg = sum([t for t in times if t is not None]) / (len(times) if len(times) > 0 else 1)  # Prevent division by zero
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out


def main():
    raw_logs = process_log_file(LOG_FILE)
    transformed_logs, active_sessions, api_call_data = transform_log_data(raw_logs)
    load_data_to_db(transformed_logs, api_call_data)
    report_content = generate_report(transformed_logs, api_call_data, active_sessions)
    with open("report.html", "w") as f:
        f.write(report_content)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == '__main__':
    main()