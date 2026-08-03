import datetime
import os
import sqlite3
import re

DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> dict:
    """Parses a single log line and returns a dictionary of its components."""
    log_pattern = re.compile(r'(?P<dt>[\d\-: ]+) (?P<lvl>\w+) (?:(?P<extra>.+)\s)?(?P<msg>.*)')
    match = log_pattern.match(line)
    if match:
        return match.groupdict()
    return {}  # Return empty dict if no match is found


def process_log_file(log_file: str) -> tuple:
    """Processes the log file and extracts error messages, session info, and API calls."""
    error_messages = []
    sessions = {}  # Active user sessions
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    lvl = parsed_line['lvl']
                    dt = parsed_line['dt']

                    if lvl == "ERROR":
                        error_messages.append({"d": dt, "t": "ERR", "m": parsed_line['msg']})
                    elif lvl == "INFO":
                        if "User" in parsed_line['msg']:
                            uid = parsed_line['msg'].split()[1]
                            action = ' '.join(parsed_line['msg'].split()[2:])
                            if "logged in" in action:
                                sessions[uid] = dt
                            elif "logged out" in action:
                                sessions.pop(uid, None)
                            error_messages.append({"d": dt, "t": "USR", "u": uid, "a": action})
                        elif "API" in parsed_line['msg']:
                            endpoint = parsed_line['msg'].split()[1]
                            duration_match = re.search(r'took (\d+)ms', line)
                            duration = int(duration_match.group(1)) if duration_match else 0
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": duration})
                    elif lvl == "WARN":
                        error_messages.append({"d": dt, "t": "WARN", "m": parsed_line['msg']})

    return error_messages, sessions, api_calls


def insert_error_data(c: sqlite3.Cursor, error_messages: list):
    """Inserts error data into the database."""
    error_count = {}
    for msg in error_messages:
        if msg['t'] == "ERR":
            error_count[msg['m']] = error_count.get(msg['m'], 0) + 1

    for msg, count in error_count.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))


def insert_api_metrics(c: sqlite3.Cursor, api_calls: list):
    """Inserts API metrics into the database."""
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
  
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))


def generate_report(error_messages: list, sessions: dict, api_calls: list):
    """Generates an HTML report from the processed data."""
    report_content = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    report_content += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg in set([msg['m'] for msg in error_messages if msg['t'] == 'ERR']):
        count = sum(1 for msg in error_messages if msg['m'] == err_msg)
        report_content += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    report_content += "</ul>\n"

    report_content += "<h2>API Latency</h2>\n<table border='1'>\n"
    report_content += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}  
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        report_content += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    report_content += "</table>\n"

    report_content += "<h2>Active Sessions</h2>\n"
    report_content += f"<p>{len(sessions)} user(s) currently active</p>\n"
    report_content += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(report_content)


def proc_data():
    """Main processing function to execute the ETL process and generate a report."""
    print("Connecting to " + DB_HOST + ":" + str(DB_PORT) + " as " + DB_USER + "...")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_messages, sessions, api_calls = process_log_file(LOG_FILE)
    insert_error_data(c, error_messages)
    insert_api_metrics(c, api_calls)
    conn.commit()
    conn.close()

    generate_report(error_messages, sessions, api_calls)
    print("Job finished at " + str(datetime.datetime.now()))

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write('2024-01-01 12:00:00 INFO User 42 logged in\n')
            f.write('2024-01-01 12:05:00 ERROR Database timeout\n')
            f.write('2024-01-01 12:05:05 ERROR Database timeout\n')
            f.write('2024-01-01 12:08:00 INFO API /users/profile took 250ms\n')
            f.write('2024-01-01 12:09:00 WARN Memory usage at 87%\n')
            f.write('2024-01-01 12:10:00 INFO User 42 logged out\n')
    proc_data()