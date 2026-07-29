import os
import re
import datetime
import sqlite3

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def read_log_file(file_path: str) -> list[dict]:
    logs = []
    log_pattern = re.compile(r'^(?P<timestamp>[^ ]+ [^ ]+) (?P<level>[^ ]+) (?P<message>.+)$')
    user_pattern = re.compile(r'User (?P<uid>\d+) logged (?P<action>.+)$')
    api_pattern = re.compile(r'API (?P<endpoint>[^ ]+) took (?P<duration>\d+)ms$')

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            log_match = log_pattern.match(line)
            if log_match:
                timestamp = log_match.group("timestamp")
                level = log_match.group("level")
                message = log_match.group("message")

                if level == "ERROR":
                    logs.append({"d": timestamp, "t": "ERR", "m": message})
                elif level == "INFO":
                    user_match = user_pattern.match(message)
                    api_match = api_pattern.match(message)
                    if user_match:
                        uid = user_match.group("uid")
                        action = user_match.group("action")
                        logs.append({"d": timestamp, "t": "USR", "u": uid, "a": action})
                    elif api_match:
                        endpoint = api_match.group("endpoint")
                        duration = int(api_match.group("duration"))
                        logs.append({"d": timestamp, "t": "API", "endpoint": endpoint, "ms": duration})
                elif level == "WARN":
                    logs.append({"d": timestamp, "t": "WARN", "m": message})
    return logs


def insert_into_db(connection: sqlite3.Connection, query: str, params: tuple):
    cursor = connection.cursor()
    cursor.execute(query, params)
    return cursor.lastrowid


def process_logs(logs: list[dict], db_connection: sqlite3.Connection):
    error_count = {}
    api_calls = {}
    active_sessions = {}

    for log in logs:
        if log["t"] == "ERR":
            msg = log["m"]
            error_count[msg] = error_count.get(msg, 0) + 1
        elif log["t"] == "USR":
            uid = log["u"]
            action = log["a"]
            if "logged in" in action:
                active_sessions[uid] = log["d"]
            elif "logged out" in action:
                active_sessions.pop(uid, None)
        elif log["t"] == "API":
            endpoint = log["endpoint"]
            duration = log["ms"]
            if endpoint not in api_calls:
                api_calls[endpoint] = []
            api_calls[endpoint].append(duration)

    # Insert error counts into the database
    for msg, count in error_count.items():
        insert_into_db(db_connection, "INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now().isoformat(), msg, count))

    # Insert API metrics into the database
    for endpoint, durations in api_calls.items():
        average_duration = sum(durations) / len(durations)
        insert_into_db(db_connection, "INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), endpoint, average_duration))

    return len(active_sessions), error_count, api_calls


def generate_report(error_count: dict, api_calls: dict, active_sessions: int) -> str:
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_count.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, durations in api_calls.items():
        avg = round(sum(durations) / len(durations), 1)
        out += f"<tr><td>{ep}</td><td>{avg}</td></tr>\n"
    out += "</table>\n<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    return out


def proc_data() -> None:
    print("Connecting to " + DB_HOST + ":" + str(DB_PORT) + " as " + DB_USER + "...")
    conn = sqlite3.connect(DB_PATH)

    # Create tables if they do not exist
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    logs = read_log_file(LOG_FILE)
    active_user_count, error_count, api_calls = process_logs(logs, conn)
    conn.commit()
    conn.close()

    report = generate_report(error_count, api_calls, active_user_count)

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