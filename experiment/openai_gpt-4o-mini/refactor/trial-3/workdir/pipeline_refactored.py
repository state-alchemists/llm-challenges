import os
import re
import sqlite3
import datetime

# Load configuration from environment variables
DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> dict:
    """Parse a log line into a structured format."""
    pattern = re.compile(r'(?P<datetime>\S+ \S+) (?P<level>\S+) (?P<message>.*)')
    match = pattern.match(line)
    if match:
        return match.groupdict()
    return {}  # Corrected return value to an empty dictionary


def process_logs() -> tuple[list, dict, list]:
    """Process the logs and return structured data."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    level = parsed_line['level']
                    dt = parsed_line['datetime']

                    if level == 'ERROR':
                        d_list.append({'d': dt, 't': 'ERR', 'm': parsed_line['message']})

                    elif level == 'INFO':
                        if 'User' in parsed_line['message']:
                            uid = parsed_line['message'].split('User ')[1].split(' ')[0]
                            action = parsed_line['message'].split('User ' + uid + ' ')[1].strip()
                            if 'logged in' in action:
                                sessions[uid] = dt
                            elif 'logged out' in action and uid in sessions:
                                sessions.pop(uid)
                            d_list.append({'d': dt, 't': 'USR', 'u': uid, 'a': action})

                        elif 'API' in parsed_line['message']:
                            endpoint = parsed_line['message'].split('API ')[1].split(' ')[0]
                            dur = re.search(r'took (\d+)ms', parsed_line['message'])
                            dur = int(dur.group(1)) if dur else 0
                            api_calls.append({'d': dt, 'endpoint': endpoint, 'ms': dur})

                    elif level == 'WARN':
                        d_list.append({'d': dt, 't': 'WARN', 'm': parsed_line['message']})

    return d_list, sessions, api_calls


def insert_error_metrics(cursor, error_metrics: dict):
    """Insert error metrics into the database."""
    for msg, count in error_metrics.items():
        cursor.execute("INSERT INTO errors VALUES (?, ?, ?)",
                       (datetime.datetime.now(), msg, count))


def insert_api_metrics(cursor, api_calls: list):
    """Insert API call metrics into the database."""
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)",
                       (datetime.datetime.now(), ep, avg))


def create_tables(cursor):
    """Create necessary tables in the database."""
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")


def generate_report(errors: dict, api_calls: list, sessions: dict) -> str:
    """Generate HTML report from processed data."""
    out = '<html>\n<head><title>System Report</title></head>\n<body>\n'
    out += '<h1>Error Summary</h1>\n<ul>\n'
    for err_msg, count in errors.items():
        out += f'<li><b>{err_msg}</b>: {count} occurrences</li>\n'
    out += '</ul>\n'

    out += '<h2>API Latency</h2>\n<table border="1">\n'
    out += '<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n'
    endpoint_stats = {call['endpoint']: [] for call in api_calls}
    for ep in endpoint_stats:
        times = [call['ms'] for call in api_calls if call['endpoint'] == ep]
        avg = sum(times) / len(times) if times else 0
        out += f'<tr><td>{ep}</td><td>{avg:.1f}</td></tr>\n'
    out += '</table>\n'

    out += '<h2>Active Sessions</h2>\n'
    out += f'<p>{len(sessions)} user(s) currently active</p>\n'
    out += '</body>\n</html>'
    return out


def main():
    """Main entry for processing data and generating report."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    create_tables(c)

    d_list, sessions, api_calls = process_logs()
    errors = {}
    for item in d_list:
        if item['t'] == 'ERR':
            msg = item['m']
            errors[msg] = errors.get(msg, 0) + 1

    insert_error_metrics(c, errors)
    insert_api_metrics(c, api_calls)

    conn.commit()
    conn.close()

    report = generate_report(errors, api_calls, sessions)

    with open('report.html', 'w') as f:
        f.write(report)

    print('Job finished at ' + str(datetime.datetime.now()))


if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write('2024-01-01 12:00:00 INFO User 42 logged in\n')
            f.write('2024-01-01 12:05:00 ERROR Database timeout\n')
            f.write('2024-01-01 12:05:05 ERROR Database timeout\n')
            f.write('2024-01-01 12:08:00 INFO API /users/profile took 250ms\n')
            f.write('2024-01-01 12:09:00 WARN Memory usage at 87%\n')
            f.write('2024-01-01 12:10:00 INFO User 42 logged out\n')
    main()