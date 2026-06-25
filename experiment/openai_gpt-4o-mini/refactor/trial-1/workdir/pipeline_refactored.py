import os
import re
import datetime
import sqlite3

# Environment variables for configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """Parses a single line from the log file and returns a dictionary of values."""
    log_regex = re.compile(r'(?P<dt>[^ ]+ [^ ]+) (?P<lvl>[A-Z]+)(?: (?P<msg>.+))?')
    match = log_regex.match(line)
    if match:
        dt = match.group('dt')
        lvl = match.group('lvl')
        msg = match.group('msg')
        return {'dt': dt, 'lvl': lvl, 'msg': msg}  # type: ignore
    return None


def process_logs() -> tuple:
    """Processes the log file and returns a structured list of data."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    dt = parsed_line['dt']
                    lvl = parsed_line['lvl']
                    msg = parsed_line['msg']

                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg})
                    elif lvl == "INFO":
                        if "User" in msg:
                            uid_match = re.search(r'User (\d+)', msg)
                            if uid_match:
                    uid = uid_match.group(1)
                            sessions[uid] = dt if "logged in" in msg else sessions.pop(uid, None)
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": msg})
                        elif "API" in msg:
                            endpoint = re.search(r'API (.+?) ', msg).group(1)
                            dur = int(re.search(r'took (\d+)ms', msg).group(1)) if "took" in msg else 0
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                    elif lvl == "WARN":
                        d_list.append({"d": dt, "t": "WARN", "m": msg})

    return d_list, sessions, api_calls


def insert_error_data(c: sqlite3.Cursor, error_data: dict):
    """Inserts error data into the database."""
    c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))


def insert_api_metric(c: sqlite3.Cursor, api_metric_data: tuple):
    """Inserts API metric data into the database."""
    c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)" , api_metric_data)


def generate_report(errors: dict, api_metrics: dict, active_sessions: int) -> str:
    """Generates an HTML report from the error and API metrics data."""
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
    """Main processing function that drives the log parsing and reporting."""
    d_list, sessions, api_calls = process_logs()

    # Database connection
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_count = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_count[msg] = error_count.get(msg, 0) + 1

    for msg, count in error_count.items():
        insert_error_data(c, (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        insert_api_metric(c, (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()

    report = generate_report(error_count, endpoint_stats, len(sessions))
    with open("report.html", "w") as f:
        f.write(report)

    print("Job finished at " + str(datetime.datetime.now()))


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