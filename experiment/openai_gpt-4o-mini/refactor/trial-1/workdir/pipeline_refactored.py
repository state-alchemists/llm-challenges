import os
import re
import sqlite3
import datetime
from typing import List, Dict, Any

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, Any]:
    """
    Parse a line from the log file.
    Returns a dictionary with parsed data.
    """
    regex = re.compile(r"^(\S+ \S+) (ERROR|INFO|WARN) (.*)$")
    match = regex.match(line.strip())
    if match:
        timestamp, level, message = match.groups()
        return {'timestamp': timestamp, 'level': level, 'message': message}
    return {'timestamp': '', 'level': '', 'message': ''}


def process_logs() -> List[Dict[str, Any]]:
    """
    Process the log file and return a list of log entries.
    """
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line['timestamp']:
                    logs.append(parsed_line)
    return logs


def insert_error_data(cursor: sqlite3.Cursor, error_data: Dict[str, int]) -> None:
    """
    Insert error data into the database.
    """
    for message, count in error_data.items():
        cursor.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), message, count))


def insert_api_metrics(cursor: sqlite3.Cursor, api_calls: List[Dict[str, Any]]) -> None:
    """
    Calculate and insert API metrics into the database.
    """
    endpoint_stats = {}
    for call in api_calls:
        endpoint = call['endpoint']
        endpoint_stats.setdefault(endpoint, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))


def generate_report(error_data: Dict[str, int], api_calls: List[Dict[str, Any]], active_sessions: int) -> None:
    """
    Generate an HTML report from the processed data.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_data.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for call in api_calls:
        out += f"<tr><td>{call['endpoint']}</td><td>{round(call['ms'], 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


def proc_data() -> None:
    """
    Main processing function that ties everything together.
    """
    logs = process_logs()
    error_data = {}
    api_calls = []
    active_sessions = 0
    sessions = {}

    for log in logs:
        level = log['level']
        message = log['message']

        if level == "ERROR":
            error_data[message] = error_data.get(message, 0) + 1

        elif level == "INFO":
            if "User" in message:
                uid = message.split()[1]
                action = ' '.join(message.split()[2:])
                if "logged in" in action:
                    sessions[uid] = log['timestamp']
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
                    active_sessions = len(sessions)
                else:
                    active_sessions = len(sessions)

            elif "API" in message:
                endpoint = message.split()[1]
                duration_match = re.search(r'took (\d+)ms', message)
                api_call_duration = int(duration_match.group(1)) if duration_match else 0
                api_calls.append({'endpoint': endpoint, 'ms': api_call_duration})

        elif level == "WARN":
            continue  # Log warning if needed

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    insert_error_data(c, error_data)
    insert_api_metrics(c, api_calls)

    conn.commit()
    conn.close()

    generate_report(error_data, api_calls, active_sessions)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()