import datetime
import os
import sqlite3
import re

# Configuration via environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """Parse a single log line into a structured format."""
    log_entry = {}
    match_info = re.match(r'^(\S+ \S+) (\w+) (.*)$', line)
    if match_info:
        timestamp, level, message = match_info.groups()
        log_entry['timestamp'] = timestamp
        log_entry['level'] = level
        log_entry['message'] = message
    return log_entry


def process_logs() -> tuple:
    """Process server logs and extract relevant data."""
    error_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_entry = parse_log_line(line)
                if not parsed_entry:
                    continue
                if parsed_entry['level'] == "ERROR":
                    error_list.append(parsed_entry['message'])
                elif "User" in parsed_entry['message']:
                    uid = re.search(r'User (\d+)', parsed_entry['message'])
                    if uid:
                        uid = uid.group(1)
                        action = parsed_entry['message'].split(' ')[-1]
                        if "logged in" in action:
                            sessions[uid] = parsed_entry['timestamp']
                        elif "logged out" in action and uid in sessions:
                            del sessions[uid]
                elif "API" in parsed_entry['message']:
                    endpoint = re.search(r'API (\/\S+)', parsed_entry['message'])
                    if endpoint:
                        duration = re.search(r'took (\d+)ms', parsed_entry['message'])
                        api_calls.append({
                            'timestamp': parsed_entry['timestamp'],
                            'endpoint': endpoint.group(1),
                            'duration': int(duration.group(1)) if duration else 0
                        })

    return error_list, sessions, api_calls


def save_to_db(error_list: list, api_calls: list) -> None:
    """Save processed data to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    # Insert errors
    error_counts = {msg: error_list.count(msg) for msg in set(error_list)}
    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    # Insert API metrics
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['duration'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(error_counts: dict, api_calls: list, active_sessions: int) -> None:
    """Generate an HTML report from the processed data."""
    output = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    output += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        output += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    output += "</ul>\n"

    output += "<h2>API Latency</h2>\n<table border='1'>\n"
    output += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {ep: sum(times) / len(times) for ep, times in api_calls}
    for ep, avg in endpoint_stats.items():
        output += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    output += "</table>\n"

    output += f"<h2>Active Sessions</h2>\n<p>{active_sessions} user(s) currently active</p>\n"
    output += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(output)


if __name__ == "__main__":
    errors, active_sessions, api_calls = process_logs()
    error_counts = {msg: errors.count(msg) for msg in set(errors)}
    save_to_db(errors, api_calls)
    generate_report(error_counts, api_calls, len(active_sessions))
    print("Job finished at " + str(datetime.datetime.now()))