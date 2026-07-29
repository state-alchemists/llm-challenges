import os
import re
import sqlite3
import datetime


def load_config() -> dict:
    """Load configuration from environment variables."""
    return {
        'db_path': os.getenv('DB_PATH', 'metrics.db'),
        'log_file': os.getenv('LOG_FILE', 'server.log'),
        'db_host': os.getenv('DB_HOST', 'localhost'),
        'db_port': int(os.getenv('DB_PORT', 5432)),
        'db_user': os.getenv('DB_USER', 'admin'),
        'db_pass': os.getenv('DB_PASS', 'password123')
    }

def parse_log_line(line: str) -> dict:
    """Parse a log line into a structured dictionary."""
    log_pattern = re.compile(r'(?P<date>\d+-\d+-\d+ \d+:\d+:\d+) (?P<level>\w+) (?P<message>.*)')
    match = log_pattern.match(line)
    if match:
        return match.groupdict()
    return {}

def process_log_file(log_file: str) -> tuple:
    """Process the log file, returning error messages, active sessions, and API calls."""
    error_messages = {}
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if not parsed_line:
                    continue
                timestamp = parsed_line['date']
                level = parsed_line['level']
                message = parsed_line['message']

                if level == 'ERROR':
                    error_messages[message] = error_messages.get(message, 0) + 1
                elif level == 'INFO':
                    if 'User' in message:
                        if 'logged in' in message:
                            uid = message.split('User ')[1].split(' ')[0]
                            sessions[uid] = timestamp
                        elif 'logged out' in message:
                            uid = message.split('User ')[1].split(' ')[0]
                            sessions.pop(uid, None)
                    elif 'API' in message:
                        endpoint = message.split('API ')[1].split(' ')[0]
                        dur = int(re.search(r'took (\d+)ms', message).group(1)) if 'took' in message else 0
                        api_calls.append({'timestamp': timestamp, 'endpoint': endpoint, 'ms': dur})
    return error_messages, sessions, api_calls

def save_to_database(db_path: str, error_messages: dict, api_calls: list) -> None:
    """Save parsed results to SQLite database."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for message, count in error_messages.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), message, count))

    endpoint_stats = {}
    for call in api_calls:
        endpoint = call['endpoint']
        endpoint_stats.setdefault(endpoint, []).append(call['ms'])

    for endpoint, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), endpoint, avg))

    conn.commit()
    conn.close()


def generate_report(error_messages: dict, api_calls: list, sessions: dict) -> str:
    """Generate the HTML report string from processed data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_messages.items():
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


def main() -> None:
    """Main function to coordinate the log processing workflow."""
    config = load_config()
    error_messages, sessions, api_calls = process_log_file(config['log_file'])
    save_to_database(config['db_path'], error_messages, api_calls)
    report = generate_report(error_messages, api_calls, sessions)
    with open("report.html", "w") as f:
        f.write(report)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == '__main__':
    main()