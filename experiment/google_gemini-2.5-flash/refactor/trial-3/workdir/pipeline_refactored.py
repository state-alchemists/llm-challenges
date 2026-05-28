import datetime
import os
import sqlite3
import re
from typing import List, Dict, Any

def get_config() -> Dict[str, str]:
    """
    Retrieves configuration from environment variables.
    """
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
    }

def extract_log_data(log_file_path: str) -> Dict[str, Any]:
    """
    Extracts data from the log file using regex.
    Returns a dictionary containing lists of errors, user sessions, and API calls.
    """
    d_list: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$"
    )
    api_pattern = re.compile(r"^\s*API /(\w+/\w+) took (\d+)ms")
    user_pattern = re.compile(r"^\s*User (\d+) (.*)")

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                match = log_pattern.match(line)
                if not match:
                    continue

                dt, lvl, raw_message = match.groups()

                if lvl == "ERROR":
                    d_list.append({"d": dt, "t": "ERR", "m": raw_message.strip()})
                elif lvl == "INFO":
                    user_match = user_pattern.search(raw_message)
                    api_match = api_pattern.search(raw_message)
                    if user_match:
                        uid, action = user_match.groups()
                        if "logged in" in action:
                            sessions[uid] = dt
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                        d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                    elif api_match:
                        endpoint, dur = api_match.groups()
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": int(dur)})
                elif lvl == "WARN":
                    d_list.append({"d": dt, "t": "WARN", "m": raw_message.strip()})
    return {"d_list": d_list, "sessions": sessions, "api_calls": api_calls}

def transform_data(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms extracted log data into summarized metrics.
    """
    d_list = extracted_data["d_list"]
    api_calls = extracted_data["api_calls"]

    error_summary: Dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    
    return {"error_summary": error_summary, "endpoint_stats": endpoint_stats}

def load_data_to_db(config: Dict[str, str], transformed_data: Dict[str, Any]):
    """
    Loads transformed data into the SQLite database using parameterized queries.
    """
    db_path = config["DB_PATH"]

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_summary = transformed_data["error_summary"]
    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    endpoint_stats = transformed_data["endpoint_stats"]
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()

def generate_report_html(error_summary: Dict[str, int], endpoint_stats: Dict[str, List[int]], sessions_count: int):
    """
    Generates the HTML report from the transformed data.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

def proc_data(config: Dict[str, str]):
    """
    Orchestrates the log processing pipeline: Extract, Transform, Load, and Report generation.
    """
    log_file_path = config["LOG_FILE"]
    
    extracted_data = extract_log_data(log_file_path)
    transformed_data = transform_data(extracted_data)
    load_data_to_db(config, transformed_data)
    generate_report_html(transformed_data["error_summary"], transformed_data["endpoint_stats"], len(extracted_data["sessions"]))

    print("Job finished at " + str(datetime.datetime.now()))


if __name__ == "__main__":
    config = get_config()
    log_file = config["LOG_FILE"]
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data(config)