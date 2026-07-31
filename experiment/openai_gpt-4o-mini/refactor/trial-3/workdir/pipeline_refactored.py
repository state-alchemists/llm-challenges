from typing import Optional
import os
import re
import sqlite3
import datetime


# Read configuration from environment variables
DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> Optional[dict]:
    """Parse a single log line and return a structured dictionary."""
    log_pattern = re.compile(r'^(?P<dt>\S+ \S+) (?P<level>\S+) (?P<msg>.*)$')
    match = log_pattern.match(line)
    if match:
        return match.groupdict()
    return None


def process_log_file(log_file: str) -> tuple:
    """Process the server log file and return a list of errors, active sessions, and API calls."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                parsed_log = parse_log_line(line)
                if parsed_log:
                    level = parsed_log['level']
                    dt = parsed_log['dt']
                    msg = parsed_log['msg']

                    if level == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg})

                    elif level == "INFO":
                        if "User" in msg:
                            uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
        if uid is not None else None if uid else None
                            if uid else None if re.search(r'User (\d+)', msg) else None
                            uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    uid = re.search(r'User (\d+)', msg)
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
if uid:
    
     
    
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
    action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
        action = msg.split("User {} ".format(uid.group(1)))[-1].strip()
                            if "logged in" in action:
                                sessions[uid.group(1)] = dt
                            elif "logged out" in action:
                                sessions.pop(uid.group(1), None)
                            d_list.append({"d": dt, "t": "USR", "u": uid.group(1), "a": action})

                        elif "API" in msg:
                            endpoint = re.search(r'API (\S+)', msg).group(1)
                            duration = int(re.search(r'took (\d+)ms', msg).group(1)) if "took" in msg else 0
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": duration})

                        elif "WARN" in level:
                            d_list.append({"d": dt, "t": "WARN", "m": msg})

    return d_list, sessions, api_calls


def insert_error_data(cursor, error_data: dict):
    """Insert error data into the database."""
    for msg in error_data:
        cursor.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                       (datetime.datetime.now(), msg, error_data[msg]))


def insert_api_metrics(cursor, api_calls: list):
    """Insert API metrics into the database."""
    endpoint_stats = {}
    for call in api_calls:
        endpoint_stats.setdefault(call["endpoint"], []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                       (datetime.datetime.now(), ep, avg))


def generate_report(error_data: dict, api_calls: list, sessions: dict) -> str:
    """Generate an HTML report from the processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_data.items():
        out += "<li><b>{}</b>: {} occurrences</li>\n".format(err_msg, count)
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}  # Collecting stats for/report generation
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])  # Grouping by endpoint
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += "<tr><td>{}</td><td>{}</td></tr>\n".format(ep, round(avg, 1))
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>{} user(s) currently active</p>\n".format(len(sessions))
    out += "</body>\n</html>"
    return out


def proc_data() -> None:
    """Main processing function to parse logs, populate database, and generate report."""
    print("Connecting to {}:{} as {}...".format(DB_HOST, DB_PORT, DB_USER))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    d_list, sessions, api_calls = process_log_file(LOG_FILE)

    error_data = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_data[msg] = error_data.get(msg, 0) + 1

    insert_error_data(c, error_data)
    insert_api_metrics(c, api_calls)

    conn.commit()
    conn.close()

    report = generate_report(error_data, api_calls, sessions)
    with open("report.html", "w") as f:
        f.write(report)

    print("Job finished at {}".format(datetime.datetime.now()))


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