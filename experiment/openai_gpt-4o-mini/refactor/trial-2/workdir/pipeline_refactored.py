import os
import re
import sqlite3
import datetime

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """
    Parse a single log line into a dictionary with relevant information.
    
    Args:
        line (str): The log line to parse.
    
    Returns:
        dict: A dictionary containing the parsed log level, date, user ID, action, endpoint, and latency.
    """
    pattern = re.compile(r'(?P<dt>\S+ \S+) (?P<lvl>\w+) (?P<msg>.+)')
    match = pattern.match(line)
    if match:
        dt = match.group('dt')
        lvl = match.group('lvl')
        msg = match.group('msg')
        if lvl == "ERROR":
            return {"d": dt, "t": "ERR", "m": msg}
        elif lvl == "INFO":
            if "User" in msg:
                uid = re.search(r'User (\d+)', msg)
                action = re.search(r'User \d+ (.+)', msg)
                if uid and action:
                    return {"d": dt, "t": "USR", "u": uid.group(1), "a": action.group(1)}
            elif "API" in msg:
                endpoint = re.search(r'API (\S+)', msg)
                dur = re.search(r'took (\d+)ms', msg)
                if endpoint:
                    return {"d": dt, "t": "API", "endpoint": endpoint.group(1), "ms": int(dur.group(1)) if dur else 0}
            elif "WARN" in msg:
                return {"d": dt, "t": "WARN", "m": msg}
    return {}


def extract_errors(d_list: list) -> dict:
    """
    Extract error messages and their occurrence counts from the data list.
    
    Args:
        d_list (list): The list containing parsed log information.
    
    Returns:
        dict: A dictionary with error messages and their counts.
    """
    errors = {}
    for entry in d_list:
        if entry.get("t") == "ERR":
            msg = entry["m"]
            errors[msg] = errors.get(msg, 0) + 1
    return errors


def calculate_api_metrics(api_calls: list) -> dict:
    """
    Calculate average latency for each API endpoint.
    
    Args:
        api_calls (list): The list containing API call information.
    
    Returns:
        dict: A dictionary with API endpoints and their average latencies.
    """
    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    avg_metrics = {ep: sum(times) / len(times) for ep, times in endpoint_stats.items()}
    return avg_metrics


def save_to_database(errors: dict, api_metrics: dict):
    """
    Saves error and API metric information to the SQLite database.
    
    Args:
        errors (dict): A dictionary of error messages and their counts.
        api_metrics (dict): A dictionary of API endpoints and their average latencies.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    for msg, count in errors.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))
    for ep, avg in api_metrics.items():
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))
    conn.commit()
    conn.close()


def generate_report(d_list: list, api_metrics: dict, sessions: dict):
    """
    Generate an HTML report summarizing the errors, API metrics, and active sessions.
    
    Args:
        d_list (list): The list containing parsed log information.
        api_metrics (dict): The API metrics to include in the report.
        sessions (dict): The active user sessions to include in the report.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_counts = extract_errors(d_list)
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"
    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_metrics.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"
    out += f"<h2>Active Sessions</h2>\n<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"
    with open("report.html", "w") as f:
        f.write(out)


def proc_data():
    """
    Process the server logs, extract relevant information, save to database, and generate report.
    """
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    if parsed_line["t"] == "USR":
                        sessions[parsed_line["u"]] = parsed_line["d"]
                    elif parsed_line["t"] == "API":
                        api_calls.append(parsed_line)
                    d_list.append(parsed_line)

    save_to_database(extract_errors(d_list), calculate_api_metrics(api_calls))
    generate_report(d_list, calculate_api_metrics(api_calls), sessions)
    print(f"Job finished at {datetime.datetime.now()}")


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