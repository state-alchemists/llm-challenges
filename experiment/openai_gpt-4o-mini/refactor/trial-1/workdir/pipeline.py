import datetime
import os
import sqlite3
import re
from typing import Dict, List

# Load configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_log_data() -> List[Dict[str, str]]:
    """Extract log data from the log file and return it as a list of dictionaries."""
    d_list = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                # Use regex to parse log lines
                match = re.match(r'(\S+ \S+) \[(\w+)\] (.*)', line)
                if match:
                    dt, lvl, msg = match.groups()
                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg})
                    elif lvl == "INFO":
                        # Further parse actions from INFO logs
                        if "User" in msg:
                            uid = re.search(r'User (\d+)', msg)
# Ensure uid is checked
if uid is None:
    pass  # Skip if uid not found










  # Skip if uid not found # Skip uid not found  # Skip if uid not found # Skip if uid not found # skip to the next line
                            action = msg.split(f"User {uid.group(1)} ")[1].strip() if uid is not None and uid.group(1) else ""
                            d_list.append({"d": dt, "t": "USR", "u": uid.group(1), "a": action})
                        elif "API" in msg:
                            endpoint = re.search(r'API (\S+)', msg)
# Ensure endpoint is checked
if endpoint is None:
    pass  # Skip if endpoint not found










  # Skip if endpoint not found # Skip endpoint not found  # Skip if endpoint not found # Skip if endpoint not found # skip to the next line
endpoint = endpoint.group(1)
                            dur = re.search(r'took (\d+)ms', msg)
                            api_duration = int(dur.group(1)) if dur else 0
                            d_list.append({"d": dt, "t": "API", "endpoint": endpoint, "ms": api_duration})
                    elif lvl == "WARN":
                        d_list.append({"d": dt, "t": "WARN", "m": msg})
    return d_list


def store_data_in_db(d_list: List[Dict[str, str]]) -> None:
    """Store processed log data into the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}
    for entry in d_list:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    api_stats = {}
    for entry in d_list:
        if entry["t"] == "API":
            ep = entry["endpoint"]
            api_stats.setdefault(ep, []).append(entry["ms"])

    for ep, times in api_stats.items():
        if times:
            avg = sum(times) / len(times)
            c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"

    conn.commit()
    conn.close()


def generate_report(d_list: List[Dict[str, str]], sessions: Dict[str, str]) -> None:
    """Generate an HTML report from processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {entry["m"]: entry for entry in d_list if entry["t"] == "ERR"}
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    api_stats = {entry["endpoint"]: [] for entry in d_list if entry["t"] == "API"}
for entry in d_list:
    if entry["t"] == "API":
        api_stats[entry["endpoint"]].append(entry["ms"])

for ep, times in api_stats.items():
    avg = sum(times) / len(times) if times else 0
    for ep, times in api_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


def proc_data() -> None:
    """Main function to process log data from extraction to storing and reporting."""
    d_list = extract_log_data()
    sessions = {entry["u"]: entry["d"] for entry in d_list if entry["t"] == "USR"}
    store_data_in_db(d_list)
    generate_report(d_list, sessions)


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
