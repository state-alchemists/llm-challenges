import os
import re
import sqlite3
import datetime

# Load configuration from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict[str, str]:
    """
    Parses a single log line and returns a dictionary containing log details.
    
    Args:
        line (str): The log line to parse.

    Returns:
        dict[str, str]: A dictionary containing parsed log details.
    """
    log_pattern = re.compile(r'(?P<timestamp>\S+ \S+) (?P<level>\S+) (?P<message>.+)')
    match = log_pattern.match(line)
    if match:
        return match.groupdict()
    return {}


def extract_api_call(line: str) -> dict[str, str]:
    """
    Extracts API call data from log line containing 'API'.
    
    Args:
        line (str): The log line.

    Returns:
        dict[str, str]: A dictionary with endpoint and duration.
    """
    endpoint_pattern = re.compile(r'API (?P<endpoint>.+?) took (?P<duration>\d+)ms')
    match = endpoint_pattern.search(line)
    if match:
        return match.groupdict()
    return {}


def process_logs():
    """
    Processes the logs and returns categorized log entries.
    
    Returns:
        tuple[list[dict], dict]: A tuple of error logs, user sessions, and API calls.
    """
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_log = parse_log_line(line)
                if parsed_log:
                    if parsed_log['level'] == "ERROR":
                        d_list.append({"d": parsed_log['timestamp'], "t": "ERR", "m": parsed_log['message']})
                    elif parsed_log['level'] == "INFO":
                        if "User" in parsed_log['message']:
                            uid = re.search("User (\d+)", parsed_log['message'])
                            if uid:
                                uid = uid.group(1)
                                action = parsed_log['message'].split(uid)[1].strip()
                                if "logged in" in action:
                                    sessions[uid] = parsed_log['timestamp']
                                elif "logged out" in action and uid in sessions:
                                    del sessions[uid]
                                d_list.append({"d": parsed_log['timestamp'], "t": "USR", "u": uid, "a": action})
                        elif "API" in parsed_log['message']:
                            api_call = extract_api_call(parsed_log['message'])
                            if api_call:
                                api_calls.append({"d": parsed_log['timestamp'], **api_call})

    return d_list, sessions, api_calls


def save_to_db(d_list: list[dict], api_calls: list[dict]):
    """
    Saves error logs and API metrics to the SQLite database.
    
    Args:
        d_list (list[dict]): Error logs.
        api_calls (list[dict]): API call metrics.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(int(call["duration"].strip()))

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(d_list: list[dict], sessions: dict, api_calls: list[dict]) -> None:
    """
    Generates an HTML report from processed log data.
    
    Args:
        d_list (list[dict]): Error logs.
        sessions (dict): Active user sessions.
        api_calls (list[dict]): API call metrics.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = {}
    for entry in d_list:
        if entry["t"] == "ERR":
            error_counts[entry["m"]] = error_counts.get(entry["m"], 0) + 1
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(int(call["duration"].strip()))
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


def proc_data():
    """
    Main processing function for handling server logs, saving data to the database and generating reports.
    """
    d_list, sessions, api_calls = process_logs()
    save_to_db(d_list, api_calls)
    generate_report(d_list, sessions, api_calls)
    

if __name__ == '__main__':
    
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()