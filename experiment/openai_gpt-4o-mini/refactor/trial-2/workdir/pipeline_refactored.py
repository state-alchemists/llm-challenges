import datetime
import os
import re
import sqlite3

# Configuration constants
DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> dict[str, str] | None:
    """Parse a single log line into its components or return None if it doesn't match."""
    log_pattern = re.compile(r'^(\S+ \S+) (INFO|ERROR|WARN) (.+)$')
    match = log_pattern.match(line)
    if not match:
        return None
    timestamp = match.group(1)
    level = match.group(2)
    message = match.group(3)
    return {'timestamp': timestamp, 'level': level, 'message': message}


def process_log_file(log_file: str) -> tuple[list[str], dict[str, str], list[dict[str, int]]]:
    """Process the log file and return structured data: errors, sessions, and api calls."""
    error_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed = parse_log_line(line)
                if parsed:
                    if parsed['level'] == 'ERROR':
                        error_list.append(parsed['message'])
                    elif parsed['level'] == 'INFO':
                        if 'User' in parsed['message']:
                            uid = parsed['message'].split()[1]
                            action = ' '.join(parsed['message'].split()[2:])
                            if "logged in" in action:
                                sessions[uid] = parsed['timestamp']
                            elif "logged out" in action and uid in sessions:
                                sessions.pop(uid)
                        elif 'API' in parsed['message']:
                            endpoint = parsed['message'].split()[1]
                            duration = re.search(r'took (\d+)ms', parsed['message'])
                            if duration:
                                api_calls.append({'timestamp': parsed['timestamp'], 'endpoint': endpoint, 'ms': int(duration.group(1))})
    return error_list, sessions, api_calls


def save_metrics_to_db(errors: list[str], api_calls: list[dict[str, int]]) -> None:
    """Save error metrics and API call metrics to the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)')

    error_counts = {msg: errors.count(msg) for msg in set(errors)}
    for msg, count in error_counts.items():
        c.execute('INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)', (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute('INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)', (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(errors: list[str], api_calls: list[dict[str, int]], sessions: dict[str, str]) -> None:
    """Generate HTML report from error and API call data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {msg: errors.count(msg) for msg in set(errors)}
    for err_msg, count in error_counts.items():
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

    with open('report.html', 'w') as f:
        f.write(out)



def proc_data() -> None:
    """Main processing function that orchestrates log processing, database updates, and report generation."""
    errors, sessions, api_calls = process_log_file(LOG_FILE)
    save_metrics_to_db(errors, api_calls)
    generate_report(errors, api_calls, sessions)
    print("Job finished at ", datetime.datetime.now())


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