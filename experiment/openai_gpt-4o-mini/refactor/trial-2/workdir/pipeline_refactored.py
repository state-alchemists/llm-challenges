import datetime
import os
import sqlite3
import re


DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def read_log_file(log_file: str) -> tuple[list, dict, list]:  # Changed return type to reflect multiple outputs
    """
    Reads the specified log file and returns a list of parsed log entries.
    """
    d_list = []
    sessions = {}
    api_calls = []

    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(r'^(\S+ \S+) (ERROR|INFO|WARN) (.*)$', line)
            if match:
                dt, lvl, msg = match.groups()
                if lvl == 'ERROR':
                    d_list.append({'d': dt, 't': 'ERR', 'm': msg})
                elif lvl == 'INFO':
                    if 'User' in msg:
                        uid_match = re.search(r'User (\d+) (.*)', msg)
                        if uid_match:
                            uid, action = uid_match.groups()
                            if 'logged in' in action:
                                sessions[uid] = dt
                            elif 'logged out' in action and uid in sessions:
                                sessions.pop(uid)
                            d_list.append({'d': dt, 't': 'USR', 'u': uid, 'a': action})
                    elif 'API' in msg:
                        api_match = re.search(r'API (\S+) took (\d+)ms', msg)
                        if api_match:
                            endpoint, dur = api_match.groups()
                            api_calls.append({'d': dt, 'endpoint': endpoint, 'ms': int(dur)})
                elif lvl == 'WARN':
                    d_list.append({'d': dt, 't': 'WARN', 'm': msg})
    return d_list, sessions, api_calls


def write_to_database(data: list, api_calls: list) -> None:
    """
    Writes parsed log data to the SQLite database with error and API metrics.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)')

    error_summary = {}
    for entry in data:
        if entry['t'] == 'ERR':
            msg = entry['m']
            error_summary[msg] = error_summary.get(msg, 0) + 1

    for msg, count in error_summary.items():
        c.execute('INSERT INTO errors VALUES (?, ?, ?)', (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute('INSERT INTO api_metrics VALUES (?, ?, ?)', (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(data: list, api_calls: list, sessions: dict) -> str:
    """
    Generates the HTML report from the log data, API metrics, and active sessions.
    """
    report = '<html>\n<head><title>System Report</title></head>\n<body>\n'
    report += '<h1>Error Summary</h1>\n<ul>\n'
    error_summary = {entry['m']: entry.get('count', 0) for entry in data if entry['t'] == 'ERR'}
    for err_msg, count in error_summary.items():
        report += f'<li><b>{err_msg}</b>: {count} occurrences</li>\n'
    report += '</ul>\n'

    report += '<h2>API Latency</h2>\n<table border="1">\n'
    report += '<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n'
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        report += f'<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n'
    report += '</table>\n'

    report += f'<h2>Active Sessions</h2>\n<p>{len(sessions)} user(s) currently active</p>\n'
    report += '</body>\n</html>'
    return report



if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write('2024-01-01 12:00:00 INFO User 42 logged in\n')
            f.write('2024-01-01 12:05:00 ERROR Database timeout\n')
            f.write('2024-01-01 12:05:05 ERROR Database timeout\n')
            f.write('2024-01-01 12:08:00 INFO API /users/profile took 250ms\n')
            f.write('2024-01-01 12:09:00 WARN Memory usage at 87%\n')
            f.write('2024-01-01 12:10:00 INFO User 42 logged out\n')

    log_data, sessions, api_calls = read_log_file(LOG_FILE)
    write_to_database(log_data, api_calls)
    report = generate_report(log_data, api_calls, sessions)
    with open('report.html', 'w') as f:
        f.write(report)
    print('Job finished at ' + str(datetime.datetime.now()))
