import datetime
import os
import re
import sqlite3
from typing import List, Dict, Tuple

# Database configuration obtained from environment variables
DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> Dict[str, str]:
    """Parses a single line of the server log and returns a structured dictionary."""
    log_pattern = re.compile(r'(?P<date>\S+ \S+) (?P<level>\S+) (?P<msg>.*)')
    match = log_pattern.match(line)
    if match:
        log_dict = match.groupdict()
        return log_dict
    return {}


def process_log_file(log_file: str) -> Tuple[List[Dict], Dict, List[Dict]]:
    """Processes the log file and returns parsed data, active sessions, and API call metrics."""
    d_list = []
    sessions = {}
    api_calls = []

    with open(log_file, 'r') as f:
        for line in f:
            log_info = parse_log_line(line)
            if log_info:
                dt = log_info['date']
                lvl = log_info['level']

                if lvl == 'ERROR':
                    d_list.append({'d': dt, 't': 'ERR', 'm': log_info['msg']})
                elif lvl == 'INFO':
                    action_info = log_info['msg']
                    if 'User' in action_info:
                        uid = action_info.split('User ')[1].split(' ')[0]
                        action = action_info.split('User ' + uid + ' ')[1].strip()
                        if 'logged in' in action:
                            sessions[uid] = dt
                        elif 'logged out' in action and uid in sessions:
                            sessions.pop(uid)
                        d_list.append({'d': dt, 't': 'USR', 'u': uid, 'a': action})
                    elif 'API' in action_info:
                        endpoint = action_info.split('API ')[1].split(' ')[0]
                        dur = re.search(r'took (\d+)ms', action_info)
                        api_calls.append({'d': dt, 'endpoint': endpoint, 'ms': int(dur.group(1)) if dur else 0})
                elif lvl == 'WARN':
                    d_list.append({'d': dt, 't': 'WARN', 'm': log_info['msg']})

    return d_list, sessions, api_calls


def insert_error_metrics(cursor: sqlite3.Cursor, error_data: List[Dict]) -> None:
    """Inserts the error metrics into the database."""
    error_counts = {}
    for error in error_data:
        if error['t'] == 'ERR':
            msg = error['m']
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))


def insert_api_metrics(cursor: sqlite3.Cursor, api_calls: List[Dict]) -> None:
    """Inserts the API call metrics into the database."""
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))


def generate_report(error_data: List[Dict], sessions: Dict, api_calls: List[Dict], output_file: str) -> None:
    """Generates an HTML report from the error and metrics data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {error['m']: error['t'] for error in error_data if error['t'] == 'ERR'}
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_metrics = {call['endpoint']: call['ms'] for call in api_calls}
    for ep, times in endpoint_metrics.items():
        out += f"<tr><td>{ep}</td><td>{round(sum(times) / len(times), 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, 'w') as f:
        f.write(out)


def proc_data() -> None:
    """Main processing function that ties everything together."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

        error_data, sessions, api_calls = process_log_file(LOG_FILE)
        insert_error_metrics(c, error_data)
        insert_api_metrics(c, api_calls)

    generate_report(error_data, sessions, api_calls, 'report.html')
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()