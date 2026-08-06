import datetime
import os
import re
import sqlite3

# Get configurations from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Function to parse log lines using regex
def parse_log_line(line: str) -> dict[str, str]:
    match = re.match(r"^(?P<date>\S+ \S+) (?P<level>\S+)(?P<message>.*)", line)
    if match and isinstance(match.groupdict(), dict):
        return match.groupdict() if match else {} if match else {} if match else {} if match else {}
    return {}, {}

from typing import Dict

# Function to process log file and return structured data
def process_log() -> tuple[list[dict], dict, list[dict]]:
    d_list = []  # List to hold error messages
    sessions = {}  # Dictionary to hold active sessions
    api_calls = []  # List to hold API call metrics

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    lvl = parsed_line['level']
                    dt = parsed_line['date']
                    msg = parsed_line['message'].strip()
                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg})
                    elif lvl == "INFO":
                        if "User" in msg:
                            uid = re.search(r"User (\d+)", msg)
                            if uid:
                                uid = uid.group(1)
                                action = msg.split("User " + uid)[1].strip()
                                if "logged in" in action:
                                    sessions[uid] = dt
                                elif "logged out" in action and uid in sessions:
                                    sessions.pop(uid)
                                d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                        elif "API" in msg:
                            endpoint = re.search(r"API (\S+)?", msg)
                            dur = re.search(r"took (\d+)ms", msg)
                            api_calls.append({
                                "d": dt,
                                "endpoint": endpoint.group(1) if endpoint else "unknown",
                                "ms": int(dur.group(1)) if dur else 0
                            })
                    elif lvl == "WARN":
                        d_list.append({"d": dt, "t": "WARN", "m": msg})
    return d_list, {uid: sessions[uid] for uid in sessions}, api_calls

# Function to insert error data into database
def insert_error_data(connection: sqlite3.Connection, errors: dict):
    cursor = connection.cursor()
    for msg, count in errors.items():
        cursor.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))
    connection.commit()

# Function to insert API metrics into database
def insert_api_metrics(connection: sqlite3.Connection, api_calls: list[dict]):
    cursor = connection.cursor()
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))
    connection.commit()

# Function to generate HTML report
def generate_report(errors: dict, api_calls: list[dict], sessions: dict) -> str:
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {call['endpoint']: call['ms'] for call in api_calls}
    for ep, ms in endpoint_stats.items():
        out += f"<tr><td>{ep}</td><td>{round(ms, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out

# Main function to orchestrate ETL process
def main():
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    errors, sessions, api_calls = process_log()
    error_counts = {msg: errors.count(msg) for msg in errors}
    insert_error_data(conn, error_counts)
    insert_api_metrics(conn, api_calls)
    report = generate_report(error_counts, api_calls, sessions)

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
    main()