import os
import re
import sqlite3
import datetime
from typing import List, Dict, Tuple

# Configuration using environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, str]:
    ":param line: A line from the log file\n    :return: A dictionary with parsed log information."
    pattern = re.compile(r'^(\S+ \S+) (ERROR|INFO|WARN) (.*)$')
    match = pattern.match(line)
    if match:
        dt, lvl, msg = match.groups()
        return {'datetime': dt, 'level': lvl, 'message': msg}
    return None


def process_logs(log_lines: List[str]) -> Tuple[List[Dict], Dict, List[Dict]]:
    sessions = {}
    d_list = []
    api_calls = []

    for line in log_lines:
        parsed_line = parse_log_line(line)
        if not parsed_line:
            continue
        dt = parsed_line['datetime']
        lvl = parsed_line['level']
        msg = parsed_line['message']

        if lvl == "ERROR":
            d_list.append({"date_time": dt, "type": "ERR", "message": msg.strip(), 'count': 1})

        elif lvl == "INFO":
            if "User" in msg:
                uid_match = re.search(r'User (\d+)', msg)
                if uid_match:
                    uid = uid_match.group(1)
                    action = msg.split('User ')[1].strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action:
                        sessions.pop(uid, None)
                        d_list.append({"date_time": dt, "type": "USR", "user": uid, "action": action})
            elif "API" in msg:
                endpoint = re.search(r'API (\S+)', msg).group(1)
                dur_match = re.search(r'took (\d+)ms', msg)  
                duration = int(dur_match.group(1)) if dur_match else 0
                api_calls.append({"date_time": dt, "endpoint": endpoint, "ms": duration})

        elif lvl == "WARN":
            d_list.append({"date_time": dt, "type": "WARN", "message": msg.strip()})

    return d_list, sessions, api_calls


def store_error_metrics(errors: List[Dict]):
    ":param errors: List of error metrics to store in the database."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (datetime TEXT, message TEXT, count INTEGER)")

    error_counts = {}  
    for error in errors:
        msg = error.get('message', '')
        error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    conn.commit()
    conn.close()


def store_api_metrics(api_calls: List[Dict]):
    ":param api_calls: List of API call metrics to store in the database."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (datetime TEXT, endpoint TEXT, avg_ms REAL)")

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(errors: List[Dict], api_calls: List[Dict], active_sessions: Dict) -> str:
    report = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    report += "<h1>Error Summary</h1>\n<ul>\n"
    for error in errors:
        report += f"<li><b>{error.get('message', 'Unknown message')}</b>: {error.get('count', 0)} occurrences</li>\n"
    report += "</ul>\n"

    report += "<h2>API Latency</h2>\n<table border='1'>\n"
    report += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for call in api_calls:
        report += f"<tr><td>{call['endpoint']}</td><td>{call['ms']}</td></tr>\n"
    report += "</table>\n"

    report += "<h2>Active Sessions</h2>\n"
    report += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    report += "</body>\n</html>"
    return report


def main():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    with open(LOG_FILE, "r") as log_file:
        log_lines = log_file.readlines()

    d_list, sessions, api_calls = process_logs(log_lines)
    store_error_metrics(d_list)
    store_api_metrics(api_calls)
    report = generate_report(d_list, api_calls, sessions)

    with open("report.html", "w") as report_file:
        report_file.write(report)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == '__main__':
    main()