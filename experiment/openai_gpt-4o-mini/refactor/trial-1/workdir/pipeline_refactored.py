import datetime
import os
import re
import sqlite3
from typing import List, Dict, Tuple

# Environment variable configuration
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict:
    """Parses a single log line into a structured format."""
    log_pattern = re.compile(r'^(\S+ \S+)\s+(\S+)\s+(.*)$')
    match = log_pattern.match(line)
    if not match:
        return None
    dt, lvl, msg = match.groups()
    return {'timestamp': dt, 'level': lvl, 'message': msg}


def process_log_file(log_file: str) -> Tuple[List[Dict], Dict[str, str], List[Dict]]:
    """Processes the log file and extracts relevant information."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line.strip())
                if not parsed_line:
                    continue
                lvl = parsed_line['level']
                msg = parsed_line['message']
                dt = parsed_line['timestamp']

                if lvl == "ERROR":
                    d_list.append({"d": dt, "t": "ERR", "m": msg})
                elif lvl == "INFO" and "User" in msg:
                    uid = msg.split("User ")[1].split(" ")[0]
                    action = msg.split("User " + uid + " ")[1].strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                elif lvl == "INFO" and "API" in msg:
                    endpoint = msg.split("API ")[1].split(" ")[0]
                    dur = re.search(r'took (\d+)ms', msg)
                    dur_value = int(dur.group(1)) if dur else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur_value})
                elif lvl == "WARN":
                    d_list.append({"d": dt, "t": "WARN", "m": msg})

    return d_list, sessions, api_calls


def save_metrics_to_db(d_list: List[Dict], api_calls: List[Dict]) -> None:
    """Saves error and API metrics to the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}  # type: Dict[str, int]
    for entry in d_list:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}  # type: Dict[str, List[int]]
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(d_list: List[Dict], api_calls: List[Dict], sessions: Dict[str, str]) -> None:
    """Generates an HTML report based on the processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {}  # type: Dict[str, int]
    for entry in d_list:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_avg = {}  # type: Dict[str, List[int]]
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_avg.setdefault(ep, []).append(call["ms"])
    for ep, times in endpoint_avg.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


def proc_data() -> None:
    """Main processing function to handle log data, save metrics, and generate reports."""
    d_list, sessions, api_calls = process_log_file(LOG_FILE)
    save_metrics_to_db(d_list, api_calls)
    generate_report(d_list, api_calls, sessions)
    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    # Initialize log file if it does not exist
    if not os.path.exists(LOG_FILE):
        # Sample log for testing
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()