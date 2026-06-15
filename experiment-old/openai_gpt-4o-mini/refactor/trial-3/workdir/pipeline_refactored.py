import datetime
import os
import re
import sqlite3
from typing import Dict, List

# Environment variable configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, str]:
    """Parses a log line into its components. Returns a dictionary with relevant data."""
    regex = r'(?P<datetime>\S+ \S+) (?P<level>\S+) (?P<message>.*)'
    match = re.match(regex, line)
    if match:
        return match.groupdict()
    return {}


def extract_data_from_logs() -> (List[Dict], Dict[str, str], List[Dict[str, int]]):
    """Extracts data from logs, returning structured error, user session, and API call info."""
    d_list = []
    sessions: Dict[str, str] = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed = parse_log_line(line)
                if not parsed:
                    continue
                lvl = parsed['level']
                dt = parsed['datetime']

                if lvl == "ERROR":
                    d_list.append({"d": dt, "t": "ERR", "m": parsed['message']})

                elif lvl == "INFO":
                    if "User" in parsed['message']:
                        uid = re.search(r'User (\d+)', parsed['message']).group(1)
                        action = parsed['message'].split("User " + uid + " ")[1].strip()
                        if "logged in" in action:
                            sessions[uid] = dt
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                        d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                    elif "API" in parsed['message']:
                        endpoint = re.search(r'API (\S+)', parsed['message']).group(1)
                        dur_matches = re.search(r'took (\d+)ms', parsed['message'])
                        dur = int(dur_matches.group(1)) if dur_matches else 0
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                elif lvl == "WARN":
                    d_list.append({"d": dt, "t": "WARN", "m": parsed['message']})

    return d_list, sessions, api_calls


def load_errors_to_db(data: List[Dict]):
    """Loads error data into the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")

    r = {}
    for x in data:
        if x["t"] == "ERR":
            msg = x["m"]
            r[msg] = r.get(msg, 0) + 1

    for msg, count in r.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    conn.commit()
    conn.close()


def load_api_metrics_to_db(api_calls: List[Dict[str, int]]):
    """Loads API call metrics into the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_html_report(errors: Dict[str, int], api_calls: List[Dict[str, int]], sessions: Dict[str, str]):
    """Generates an HTML report from the given data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for call in api_calls:
        out += f"<tr><td>{call['endpoint']}</td><td>{round(call['ms'], 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)
        

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    log_data, sessions, api_calls = extract_data_from_logs()
    load_errors_to_db(log_data)
    load_api_metrics_to_db(api_calls)
    errors = {x['m']: x for x in log_data if x['t'] == 'ERR'}
    generate_html_report(errors, api_calls, sessions)
    print("Job finished at " + str(datetime.datetime.now()))
