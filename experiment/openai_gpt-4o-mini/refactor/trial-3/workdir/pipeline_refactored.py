import datetime
import os
import re
import sqlite3


# Load environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """Parses a single log line and returns a structured dictionary."""
    regex = r'^(?P<timestamp>[^ ]+ [^ ]+) (?P<level>[^ ]+) (?P<msg>.*)$'
    match = re.match(regex, line)
    if match:
        return match.groupdict()
    return None


def extract_errors(log_lines: list) -> list:
    """Extracts error messages from log lines."""
    errors = []
    for line in log_lines:
        parsed = parse_log_line(line)
        if parsed and parsed['level'] == 'ERROR':
            errors.append(parsed['msg'])
    return errors


def extract_api_calls(log_lines: list) -> list:
    """Extracts API call details from log lines."""
    api_calls = []
    for line in log_lines:
        parsed = parse_log_line(line)
        if parsed and parsed['level'] == 'INFO' and 'API' in parsed['msg']:
            endpoint = re.search(r'API ([^ ]+)', parsed['msg'])
            duration = re.search(r'took (\d+)ms', parsed['msg'])
            if endpoint and duration:
                api_calls.append({"endpoint": endpoint.group(1), "ms": int(duration.group(1))})
    return api_calls


def update_database(errors: list, api_calls: list) -> None:
    """Updates the SQLite database with error and API call information."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {msg: errors.count(msg) for msg in set(errors)}
    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(errors: list, api_calls: list, active_sessions: int) -> None:
    """Generates an HTML report from processed data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg in set(errors):
        out += "<li><b>" + err_msg + "</b>: " + str(errors.count(err_msg)) + " occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {call['endpoint']: [] for call in api_calls}
    for call in api_calls:
        endpoint_stats[call['endpoint']].append(call['ms'])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += "<tr><td>" + ep + "</td><td>" + str(round(avg, 1)) + "</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>" + str(active_sessions) + " user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)



def proc_data() -> None:
    """Main data processing function."""
    log_lines = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            log_lines = f.readlines()

    errors = extract_errors(log_lines)
    api_calls = extract_api_calls(log_lines)
    active_sessions = sum(1 for line in log_lines if 'User' in line and 'logged in' in line)
    update_database(errors, api_calls)
    generate_report(errors, api_calls, active_sessions)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()