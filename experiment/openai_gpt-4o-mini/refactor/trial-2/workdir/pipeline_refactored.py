import datetime
import os
import re
import sqlite3


def get_env_variables() -> dict:
    """Retrieve environment variables for database and log file configuration."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": int(os.getenv("DB_PORT", 5432)),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def parse_log_line(line: str) -> dict:
    """Parse a single line of log and return a dictionary of its contents."""
    log_pattern = re.compile(r'^(?P<date>[^ ]+ [^ ]+) (?P<level>[^ ]+) (?P<message>.*)$')
    match = log_pattern.match(line)
    if match:
        return match.groupdict()
    return {}


def process_logs(log_file: str) -> tuple:
    """Process logs and return parsed data lists."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    lvl = parsed_line['level']
                    dt = parsed_line['date']
                    message = parsed_line['message']

                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": message})

                    elif lvl == "INFO":
                        if "User" in message:
                            uid = message.split()[1]
                            action = message.split(f"User {uid} ")[1].strip()
                            if "logged in" in action:
                                sessions[uid] = dt
                            elif "logged out" in action and uid in sessions:
                                sessions.pop(uid)
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                        elif "API" in message:
                            endpoint = message.split()[1]
                            dur = re.search(r'took (\d+)ms', message)
                            dur_value = int(dur.group(1)) if dur else 0
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur_value})

                    elif lvl == "WARN":
                        d_list.append({"d": dt, "t": "WARN", "m": message.strip()})

    return d_list, sessions, api_calls


def connect_db(db_path: str):
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    return conn


def store_error_data(conn, errors: dict):
    """Store error data in the database."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    for msg, count in errors.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", 
                   (datetime.datetime.now(), msg, count))


def store_api_metrics(conn, api_metrics: dict):
    """Store API metrics in the database."""
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    for endpoint, times in api_metrics.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", 
                   (datetime.datetime.now(), endpoint, avg))


def generate_report(errors: dict, api_metrics: dict, active_sessions: int) -> str:
    """Generate an HTML report from the error and metrics data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_metrics.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"
    out += f"<h2>Active Sessions</h2>\n<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    return out


def proc_data():
    env_vars = get_env_variables()
    db_path = env_vars['db_path']
    log_file = env_vars['log_file']

    d_list, sessions, api_calls = process_logs(log_file)
    errors = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            errors[msg] = errors.get(msg, 0) + 1

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    with connect_db(db_path) as conn:
        store_error_data(conn, errors)
        store_api_metrics(conn, endpoint_stats)

    report = generate_report(errors, endpoint_stats, len(sessions))

    with open("report.html", "w") as f:
        f.write(report)

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    if not os.path.exists(os.getenv('LOG_FILE', 'server.log')):
        with open(os.getenv('LOG_FILE', 'server.log'), "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()