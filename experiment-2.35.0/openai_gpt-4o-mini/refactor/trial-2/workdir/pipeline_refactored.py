import datetime
import os
import sqlite3
import re


# Load configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """Parse a log line into structured data."""
    log_pattern = r'(?P<date>\S+ \S+) (?P<level>\S+) (?P<message>.*)'
    match = re.match(log_pattern, line)
    if match:
        return match.groupdict()
    return None


def process_error_logs(lines: list) -> list:
    """Process error logs and return a structured list of errors."""
    d_list = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed and parsed['level'] == 'ERROR':
            d_list.append({"d": parsed['date'], "t": "ERR", "m": parsed['message']})
    return d_list


def process_user_logs(lines: list, sessions: dict) -> list:
    """Process user logs and return a structured list of user actions."""
    d_list = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            if "User" in parsed['message']:
                uid_match = re.search(r'User (\d+)', parsed['message'])
                if uid_match:
                    uid = uid_match.group(1)
                    action = parsed['message'].split(f'User {uid} ')[1].strip()
                    if "logged in" in action:
                        sessions[uid] = parsed['date']
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": parsed['date'], "t": "USR", "u": uid, "a": action})
    return d_list


def process_api_logs(lines: list) -> list:
    """Process API call logs and return a structured list of API calls."""
    api_calls = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed and "API" in parsed['message']:
            endpoint_match = re.search(r'API (\S+)', parsed['message'])
            duration_match = re.search(r'took (\d+)ms', parsed['message'])
            if endpoint_match:
                endpoint = endpoint_match.group(1)
                dur = int(duration_match.group(1)) if duration_match else 0
                api_calls.append({"d": parsed['date'], "endpoint": endpoint, "ms": dur})
    return api_calls


def store_logs_in_db(d_list: list, api_calls: list) -> None:
    """Store processed logs into the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_count = {}
    for item in d_list:
        if item["t"] == "ERR":
            error_count[item["m"]] = error_count.get(item["m"], 0) + 1

    for msg, count in error_count.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(d_list: list, api_calls: list, sessions: dict) -> None:
    """Generate an HTML report from processed data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_summary = {}
    for item in d_list:
        if item["t"] == "ERR":
            error_summary[item["m"]] = error_summary.get(item["m"], 0) + 1
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += f"<h2>Active Sessions</h2>\n<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>\n"

    with open("report.html", "w") as f:
        f.write(out)



def proc_data():
    """Main processing function to control the ETL pipeline."""
    sessions = {}

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        d_list = process_error_logs(lines) + process_user_logs(lines, sessions) + process_api_logs(lines)
        store_logs_in_db(d_list, process_api_logs(lines))
        generate_report(d_list, process_api_logs(lines), sessions)
        print("Job finished at " + str(datetime.datetime.now()))
    else:
        print(f"Log file {LOG_FILE} does not exist.")


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
