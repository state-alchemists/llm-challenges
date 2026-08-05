import os
import re
import sqlite3
import datetime
from typing import List, Dict, Any

# Load configurations from environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> Dict[str, Any]:
    """
    Parse a single log line and return its components.
    
    :param line: A line from the server log.
    :return: A dictionary containing log details.
    """
    parts = line.split(" ")
    if len(parts) < 3:
        return {}
    lvl = parts[2]
    dt = "{} {}".format(parts[0], parts[1])

    if lvl == "ERROR":
        message = " ".join(parts[3:]).strip()
        return {"date": dt, "type": "ERR", "message": message}
    elif lvl == "INFO":
        if "User" in line:
            uid = line.split("User ")[1].split(" ")[0]
            action = line.split("User {} ".format(uid))[1].strip()
            return {"date": dt, "type": "USR", "user": uid, "action": action}
        elif "API" in line:
            endpoint = line.split("API ")[1].split(" ")[0]
            duration = line.split("took ")[1].split("ms")[0] if "took" in line else "0"
            return {"date": dt, "type": "API", "endpoint": endpoint, "duration": int(duration)}
    elif lvl == "WARN":
        message = " ".join(parts[3:]).strip()
        return {"date": dt, "type": "WARN", "message": message}
    return {}


def load_logs() -> List[Dict[str, Any]]:
    """
    Load and parse logs from the log file.
    
    :return: A list of dictionaries representing parsed log entries.
    """
    log_entries = []
    if not os.path.exists(LOG_FILE):
        return log_entries
    with open(LOG_FILE, "r") as f:
        for line in f:
            entry = parse_log_line(line)
            if entry:
                log_entries.append(entry)
    return log_entries


def process_logs(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process log entries and extract relevant metrics.
    
    :param log_entries: A list of parsed log entries.
    :return: A dictionary containing error counts, session details, and API latency.
    """
    error_counts = {}
    sessions = {}
    api_calls = []

    for entry in log_entries:
        if entry["type"] == "ERR":
            msg = entry["message"]
            error_counts[msg] = error_counts.get(msg, 0) + 1
        elif entry["type"] == "USR":
            uid = entry["user"]
            dt = entry["date"]
            if "logged in" in entry["action"]:
                sessions[uid] = dt
            elif "logged out" in entry["action"] and uid in sessions:
                sessions.pop(uid)
        elif entry["type"] == "API":
            api_calls.append(entry)

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["duration"])

    return {
        "error_counts": error_counts,
        "sessions": sessions,
        "endpoint_stats": endpoint_stats
    }


def save_to_database(metrics: Dict[str, Any]) -> None:
    """
    Save processed metrics to the database.
    
    :param metrics: A dictionary containing metrics to be saved.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    now = datetime.datetime.now()

    for msg, count in metrics["error_counts"].items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (now, msg, count))

    for ep, times in metrics["endpoint_stats"].items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)" , (now, ep, avg))

    conn.commit()
    conn.close()


def generate_report(metrics: Dict[str, Any]) -> None:
    """
    Generate an HTML report based on the metrics.
    
    :param metrics: A dictionary containing metrics for the report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics["error_counts"].items():
        out += "<li><b>{}</b>: {} occurrences</li>\n".format(err_msg, count)
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in metrics["endpoint_stats"].items():
        avg = sum(times) / len(times)
        out += "<tr><td>{}</td><td>{}</td></tr>\n".format(ep, round(avg, 1))
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>{} user(s) currently active</p>\n".format(len(metrics["sessions"]))
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)



def proc_data():
    log_entries = load_logs()
    metrics = process_logs(log_entries)
    save_to_database(metrics)
    generate_report(metrics)


if __name__ == "__main__":
    proc_data()
