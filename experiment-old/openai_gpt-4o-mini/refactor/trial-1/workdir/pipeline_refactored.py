import os
import re
import sqlite3
import datetime
from typing import List, Dict

DB_PATH = os.environ.get('DB_PATH', 'metrics.db')
LOG_FILE = os.environ.get('LOG_FILE', 'server.log')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = int(os.environ.get('DB_PORT', '5432'))
DB_USER = os.environ.get('DB_USER', 'admin')
DB_PASS = os.environ.get('DB_PASS', 'password123')


def parse_log_line(line: str) -> Dict:
    """
    Parses a single log line.
    Returns a dictionary with the log type and relevant information.
    """
    regex = r'^(?P<dt>\S+ \S+) (?P<lvl>\w+) (?P<msg>.*)$'
    match = re.match(regex, line)
    if match:
        level = match.group('lvl')
        timestamp = match.group('dt')
        message = match.group('msg')
        return {'level': level, 'timestamp': timestamp, 'message': message}
    return {}


def extract_data(log_file: str) -> (List[Dict], Dict[str, str], List[Dict]):
    """
    Extracts data from the log file.
    Returns a list of dictionaries for errors, user sessions, and API calls.
    """
    d_list = []
    sessions = {}
    api_calls = []
    
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if not parsed_line:
                    continue
                level = parsed_line['level']
                dt = parsed_line['timestamp']
                if level == 'ERROR':
                    d_list.append({'d': dt, 't': 'ERR', 'm': parsed_line['message']})
                elif level == 'INFO' and 'User' in parsed_line['message']:
                    uid = re.search(r'User (\d+)', parsed_line['message']).group(1)
                    action = parsed_line['message'].split('User ' + uid + ' ')[1].strip()
                    if 'logged in' in action:
                        sessions[uid] = dt
                    elif 'logged out' in action:
                        if uid in sessions:
                            sessions.pop(uid)
                    d_list.append({'d': dt, 't': 'USR', 'u': uid, 'a': action})
                elif level == 'INFO' and 'API' in parsed_line['message']:
                    endpoint = re.search(r'API (\\S+)', parsed_line['message']).group(1)
                    dur = int(re.search(r'took (\d+)ms', parsed_line['message']).group(1)) if 'took' in parsed_line['message'] else 0
                    api_calls.append({'d': dt, 'endpoint': endpoint, 'ms': dur})
                elif level == 'WARN':
                    d_list.append({'d': dt, 't': 'WARN', 'm': parsed_line['message']})
    return d_list, sessions, api_calls


def insert_errors(c: sqlite3.Cursor, d_list: List[Dict]) -> None:
    """
    Inserts error messages into the database.
    """
    error_count = {}
    for x in d_list:
        if x['t'] == 'ERR':
            msg = x['m']
            error_count[msg] = error_count.get(msg, 0) + 1
    for msg, count in error_count.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))


def insert_api_metrics(c: sqlite3.Cursor, api_calls: List[Dict]) -> None:
    """
    Inserts API call metrics into the database.
    """
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))


def generate_report(d_list: List[Dict], sessions: Dict[str, str], api_calls: List[Dict]) -> str:
    """
    Generates the HTML report from the provided data.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_count = {}
    for x in d_list:
        if x['t'] == 'ERR':
            msg = x['m']
            error_count[msg] = error_count.get(msg, 0) + 1
    for err_msg, count in error_count.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    return out


def proc_data() -> None:
    """
    Main process that coordinates the data extraction, transformation, loading, and reporting.
    """
    d_list, sessions, api_calls = extract_data(LOG_FILE)
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        insert_errors(c, d_list)
        insert_api_metrics(c, api_calls)
    report = generate_report(d_list, sessions, api_calls)
    with open('report.html', 'w') as f:
        f.write(report)
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