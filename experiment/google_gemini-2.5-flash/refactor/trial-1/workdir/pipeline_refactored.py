import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts log data from the specified log file, parsing error, user, and API events.

    Args:
        log_file_path: The path to the server log file.

    Returns:
        A tuple containing:
            - A list of parsed data dictionaries (errors, user actions, warnings).
            - A dictionary of active user sessions (user_id: login_datetime).
            - A list of API call dictionaries.
    """
    parsed_data: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    log_pattern = re.compile(
        r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
        r"(?P<level>INFO|ERROR|WARN) "
        r"(?P<message>.*)$"
    )
    user_login_pattern = re.compile(r"User (?P<user_id>\w+) logged in")
    user_logout_pattern = re.compile(r"User (?P<user_id>\w+) logged out")
    api_call_pattern = re.compile(r"API (?P<endpoint>/\S+) took (?P<duration>\d+)ms")

    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return parsed_data, sessions, api_calls

    with open(log_file_path, "r") as f:
        for line in f:
            match = log_pattern.match(line)
            if not match:
                continue

            dt = match.group("datetime")
            level = match.group("level")
            message = match.group("message").strip()

            if level == "ERROR":
                parsed_data.append({"d": dt, "t": "ERR", "m": message})
            elif level == "INFO":
                user_login_match = user_login_pattern.match(message)
                user_logout_match = user_logout_pattern.match(message)
                api_call_match = api_call_pattern.match(message)

                if user_login_match:
                    uid = user_login_match.group("user_id")
                    sessions[uid] = dt
                    parsed_data.append({"d": dt, "t": "USR", "u": uid, "a": f"User {uid} logged in"})
                elif user_logout_match:
                    uid = user_logout_match.group("user_id")
                    if uid in sessions:
                        sessions.pop(uid)
                    parsed_data.append({"d": dt, "t": "USR", "u": uid, "a": f"User {uid} logged out"})
                elif api_call_match:
                    endpoint = api_call_match.group("endpoint")
                    duration = int(api_call_match.group("duration"))
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": duration})
            elif level == "WARN":
                parsed_data.append({"d": dt, "t": "WARN", "m": message})
    return parsed_data, sessions, api_calls


def transform_data(
    parsed_data: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms extracted log data into error summaries and API latency statistics.

    Args:
        parsed_data: A list of parsed data dictionaries.
        api_calls: A list of API call dictionaries.

    Returns:
        A tuple containing:
            - A dictionary of error messages and their counts.
            - A dictionary of API endpoints and a list of their latencies.
    """
    error_summary: Dict[str, int] = {}
    for item in parsed_data:
        if item["t"] == "ERR":
            msg = item["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_latencies: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint = call["endpoint"]
        endpoint_latencies.setdefault(endpoint, []).append(call["ms"])

    return error_summary, endpoint_latencies


def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
) -> None:
    """
    Loads transformed data into an SQLite database.

    Args:
        db_path: The path to the SQLite database file.
        error_summary: A dictionary of error messages and their counts.
        endpoint_latencies: A dictionary of API endpoints and a list of their latencies.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_summary: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html",
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        endpoint_latencies: A dictionary of API endpoints and a list of their latencies.
        active_sessions_count: The number of currently active user sessions.
        output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)


def main():
    """
    Main function to orchestrate log data processing, database loading, and report generation.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    parsed_data, sessions, api_calls = extract_log_data(LOG_FILE)
    error_summary, endpoint_latencies = transform_data(parsed_data, api_calls)
    load_data_to_db(DB_PATH, error_summary, endpoint_latencies)
    generate_report(error_summary, endpoint_latencies, len(sessions))

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
    main()
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(LOG_FILE):
        f = open(LOG_FILE, "r")
        for line in f:
            s = line.split(" ")
            if len(s) > 3:
                lvl = s[2]
                dt = s[0] + " " + s[1]

                if lvl == "ERROR":
                    m = ""
                    for i in range(3, len(s)):
                        m += s[i] + " "
                    d_list.append({"d": dt, "t": "ERR", "m": m.strip()})

                elif lvl == "INFO" and "User" in line:
                    uid = line.split("User ")[1].split(" ")[0]
                    action = line.split("User " + uid + " ")[1].strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})

                elif lvl == "INFO" and "API" in line:
                    endpoint = line.split("API ")[1].split(" ")[0]
                    dur = line.split("took ")[1].split("ms")[0] if "took" in line else "0"
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": int(dur)})

                elif lvl == "WARN":
                    m = " ".join(s[3:]).strip()
                    d_list.append({"d": dt, "t": "WARN", "m": m})
        f.close()

    print("Connecting to " + DB_HOST + ":" + str(DB_PORT) + " as " + DB_USER + "...")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    r = {}
    for x in d_list:
        if x["t"] == "ERR":
            msg = x["m"]
            r[msg] = r.get(msg, 0) + 1

    for msg, count in r.items():
        c.execute(
            "INSERT INTO errors VALUES ('%s', '%s', %d)"
            % (datetime.datetime.now(), msg, count)
        )

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics VALUES ('%s', '%s', %f)"
            % (datetime.datetime.now(), ep, avg)
        )

    conn.commit()
    conn.close()

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in r.items():
        out += "<li><b>" + err_msg + "</b>: " + str(count) + " occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += "<tr><td>" + ep + "</td><td>" + str(round(avg, 1)) + "</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += "<p>" + str(len(sessions)) + " user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)

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
