import os
import re
import datetime
import sqlite3
from typing import List, Dict, Tuple

# Load configuration from environment variables
DB_PATH = os.getenv('DB_PATH', 'metrics.db')
LOG_FILE = os.getenv('LOG_FILE', 'server.log')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASS', 'password123')


def parse_log_line(line: str) -> Tuple[str, str, str]:
    """Parses a single line of the log file and returns relevant data."""
    log_pattern = re.compile(r'(?P<datetime>\S+ \S+) (?P<level>\w+) (?P<message>.*)')
    match = log_pattern.match(line)
    if match:
        return match.group('datetime'), match.group('level'), match.group('message')
    return '', '', ''


def process_logs() -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, Tuple[str, int]]]]:
    """Processes the log file and returns a list of entries, session data, and API call metrics."""
    entries = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    dt_str, lvl, msg = parsed_line
                    if lvl == "ERROR":
                        entries.append({"d": dt_str, "t": "ERR", "m": msg})
                    elif lvl == "INFO":
                        if "User" in msg:
                            uid = msg.split()[1]
                            action = msg.split('User {} '.format(uid))[1]
                            if "logged in" in action:
                                sessions[uid] = dt_str
                            elif "logged out" in action and uid in sessions:
                                sessions.pop(uid)
                            entries.append({"d": dt_str, "t": "USR", "u": uid, "a": action})
                        elif "API" in msg:
                            endpoint = msg.split('API ')[1].split()[0]
                            dur_match = re.search(r'took (\d+)ms', msg)
                            dur = int(dur_match.group(1)) if dur_match else 0
                            api_calls.append({"d": dt_str, "endpoint": endpoint, "ms": dur})
                    elif lvl == "WARN":
                        entries.append({"d": dt_str, "t": "WARN", "m": msg})
    return entries, sessions, api_calls


def save_metrics_to_db(entries: List[Dict[str, str]], api_calls: List[Dict[str, Tuple[str, int]]]) -> None:
    """Saves error and API metrics to the database."""
    print("Connecting to {}:{} as {}...".format(DB_HOST, DB_PORT, DB_USER))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_count = {}  # For counting unique error messages
    for entry in entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_count[msg] = error_count.get(msg, 0) + 1

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


def generate_report(entries: List[Dict[str, str]], sessions: Dict[str, str], api_calls: List[Dict[str, Tuple[str, int]]]) -> None:
    """Generates an HTML report from the processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_count = {}

    for entry in entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_count[msg] = error_count.get(msg, 0) + 1

    for err_msg, count in error_count.items():
        out += "<li><b>{}</b>: {} occurrences</li>\n".format(err_msg, count)
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += "<tr><td>{}</td><td>{}</td></tr>\n".format(ep, round(avg, 1))
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>{} user(s) currently active</p>\n".format(len(sessions))
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

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

    entries, sessions, api_calls = process_logs()
    save_metrics_to_db(entries, api_calls)
    generate_report(entries, sessions, api_calls)