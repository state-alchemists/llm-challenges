import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Optional, Any

def _load_config() -> Dict[str, Any]:
    """Loads configuration from environment variables with default fallbacks."""
    return {
        "DB_PATH": os.getenv("DB_PATH", "metrics.db"),
        "LOG_FILE": os.getenv("LOG_FILE", "server.log"),
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": int(os.getenv("DB_PORT", "5432")),
        "DB_USER": os.getenv("DB_USER", "admin"),
        "DB_PASS": os.getenv("DB_PASS", "password123"),
        "REPORT_FILE": os.getenv("REPORT_FILE", "report.html"),
    }



def _parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parses a single log line using regex and returns structured data."""
    # Regex to capture timestamp, log level, and the rest of the message
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$", line)
    if not match:
        return None

    dt_str, lvl, message = match.groups()

    if lvl == "ERROR":
        return {"d": dt_str, "t": "ERR", "m": message.strip()}

    elif lvl == "INFO" and "User" in message:
        user_match = re.match(r"User (\d+) (.*)", message)
        if user_match:
            uid, action = user_match.groups()
            return {"d": dt_str, "t": "USR", "u": uid, "a": action.strip()}

    elif lvl == "INFO" and "API" in message:
        api_match = re.match(r"API (\S+) took (\d+)ms", message)
        if api_match:
            endpoint, dur = api_match.groups()
            return {"d": dt_str, "t": "API", "endpoint": endpoint, "ms": int(dur)}
        # Handle API calls without 'took NNNms' (duration defaults to 0)
        api_match_no_duration = re.match(r"API (\S+)", message)
        if api_match_no_duration:
            endpoint = api_match_no_duration.groups()[0]
            return {"d": dt_str, "t": "API", "endpoint": endpoint, "ms": 0}

    elif lvl == "WARN":
        return {"d": dt_str, "t": "WARN", "m": message.strip()}
    
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict], Dict[str, str], List[Dict]]:
    """Reads and parses the log file, extracting errors, sessions, and API calls."""
    d_list: List[Dict] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict] = []

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return d_list, sessions, api_calls

    with open(log_file_path, "r") as f:
        for line in f:
            parsed_line = _parse_log_line(line)
            if parsed_line:
                d_list.append(parsed_line)
                if parsed_line["t"] == "USR":
                    uid = parsed_line["u"]
                    action = parsed_line["a"]
                    if "logged in" in action:
                        sessions[uid] = parsed_line["d"]
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                elif parsed_line["t"] == "API":
                    api_calls.append(parsed_line)

    return d_list, sessions, api_calls

def transform_data(d_list: List[Dict], api_calls: List[Dict]) -> Tuple[Dict[str, int], Dict[str, float]]:
    """Transforms raw log data into error counts and API latency averages."""
    error_summary: Dict[str, int] = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_latency_avg: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        api_latency_avg[ep] = avg
    
    return error_summary, api_latency_avg

def load_to_database(db_path: str, error_summary: Dict[str, int], api_latency_avg: Dict[str, float]) -> None:
    """Loads the processed data into the SQLite database."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, avg in api_latency_avg.items():
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()

def generate_report(report_file_path: str, error_summary: Dict[str, int], api_latency_avg: Dict[str, float], active_sessions_count: int) -> None:
    """Generates an HTML report from the processed data."""
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
    for ep, avg in api_latency_avg.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_file_path, "w") as f:
        f.write(out)

def main():
    """Main function to orchestrate the log processing and reporting pipeline."""
    config = _load_config()
    db_path = config["DB_PATH"]
    log_file_path = config["LOG_FILE"]
    report_file_path = config["REPORT_FILE"]
    db_host = config["DB_HOST"]
    db_port = config["DB_PORT"]
    db_user = config["DB_USER"]

    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    d_list, sessions, api_calls = extract_log_data(log_file_path)
    error_summary, api_latency_avg = transform_data(d_list, api_calls)
    load_to_database(db_path, error_summary, api_latency_avg)
    generate_report(report_file_path, error_summary, api_latency_avg, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    config = _load_config()
    log_file_path = config["LOG_FILE"]
    if not os.path.exists(log_file_path):
        with open(log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
