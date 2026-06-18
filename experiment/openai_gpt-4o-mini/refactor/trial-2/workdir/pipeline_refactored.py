import datetime
import os
import re
import sqlite3
from typing import List, Dict

# Configuration settings from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, str]:
    match = re.match(r'(?P<date>[^ ]+ [^ ]+) (?P<level>[^ ]+) (?P<message>.*)', line)
    if match:
        return match.groupdict()
    return {}


def process_logs() -> List[Dict[str, str]]:
    d_list = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    dt = parsed_line['date']
                    lvl = parsed_line['level']
                    msg = parsed_line['message']
                    if lvl == "ERROR":
                        d_list.append({"d": dt, "t": "ERR", "m": msg.strip()})
                    elif lvl == "INFO":
                        if "User" in msg:
                            uid = msg.split('User ')[1].split()[0]
                            action = msg.split('User ' + uid + ' ')[1].strip()
                            d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                        elif "API" in msg:
                            endpoint = msg.split("API ")[1].split()[0]
                            dur = int(msg.split("took ")[1].split("ms")[0]) if "took" in msg else 0
                            d_list.append({"d": dt, "t": "API", "endpoint": endpoint, "ms": dur})
                        elif "WARN" in msg:
                            d_list.append({"d": dt, "t": "WARN", "m": msg.strip()})
    return d_list


def save_to_database(data: List[Dict[str, str]]) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_counts = {}
    api_calls = []
    for item in data:
        if item['t'] == 'ERR':
            msg = item['m']
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif item['t'] == 'API':
            api_calls.append(item)
    
    for msg, count in error_counts.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    for call in api_calls:
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (datetime.datetime.now(), call['endpoint'], call['ms']))

    conn.commit()
    conn.close()


def generate_report(data: List[Dict[str, str]]) -> None:
    error_counts = {item['m']: item['c'] for item in data if item['t'] == 'ERR'}
    endpoint_stats = {item['endpoint']: [] for item in data if item['t'] == 'API'}
    
    for item in data:
        if item['t'] == 'API':
            endpoint_stats[item['endpoint']].append(item['ms'])

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>0 user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


if __name__ == "__main__":
    log_data = process_logs()
    save_to_database(log_data)
    generate_report(log_data)
    print("Job finished at " + str(datetime.datetime.now()))
