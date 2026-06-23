import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any, Tuple

# Load configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, Any]:
    """Parse a log line into a structured dictionary."""
    pattern = r'^(?P<datetime>\S+ \S+) (?P<level>\S+) (?P<message>.+)$'
    match = re.match(pattern, line)
    if match:
        return match.groupdict()
    return {}


def process_log_file(log_file: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """Process the log file and return structured log entries."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    lvl = parsed_line["level"]
                    dt = parsed_line["datetime"]
                    msg = parsed_line["message"]

                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg.strip()})
                    elif lvl == "INFO":
                        if "User" in msg:
                            uid = msg.split("User ")[1].split(" ")[0]
                            action = msg.split("User " + uid + " ")[1].strip()
                            if "logged in" in action:
                                sessions[uid] = dt
                            elif "logged out" in action and uid in sessions:
                                sessions.pop(uid)
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                        elif "API" in msg:
                            endpoint = msg.split("API ")[1].split(" ")[0]
                            dur = int(msg.split("took ")[1].split("ms")[0]) if "took" in msg else 0
                            api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                    elif lvl == "WARN":
                        d_list.append({"d": dt, "t": "WARN", "m": msg.strip()})
    return d_list, sessions, api_calls


def save_to_database(d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]) -> None:
    """Save error and API metrics to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}  # to hold error messages and their counts
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}  # to compute average latencies for API calls
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]], sessions: Dict[str, str]) -> None:
    """Generate an HTML report based on the processed data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_summary = {msg: sum(1 for x in d_list if x['t'] == 'ERR' and x['m'] == msg) for msg in set(x['m'] for x in d_list if x['t'] == 'ERR')}
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}  # to accumulate latency times
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)



def proc_data() -> None:
    """Main data processing function to orchestrate the ETL operation."""
    log_entries, sessions, api_calls = process_log_file(LOG_FILE)
    save_to_database(log_entries, api_calls)
    generate_report(log_entries, api_calls, sessions)
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