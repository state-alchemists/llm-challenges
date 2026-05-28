import os
import re
import sqlite3
import datetime


def get_env_variables() -> dict:
    """Retrieve environment variables necessary for configuration."""
    return {
        'DB_PATH': os.getenv('DB_PATH', 'metrics.db'),
        'LOG_FILE': os.getenv('LOG_FILE', 'server.log'),
        'DB_HOST': os.getenv('DB_HOST', 'localhost'),
        'DB_PORT': int(os.getenv('DB_PORT', 5432)),
        'DB_USER': os.getenv('DB_USER', 'admin'),
        'DB_PASS': os.getenv('DB_PASS', 'password123')
    }


def parse_log_line(line: str) -> dict:
    """Parse an individual line from the server log. Return a dictionary of log details."""
    log_pattern = re.compile(r'^(?P<date>\S+ \S+) (?P<level>\S+) ?(?P<user_action>User (?P<uid>\d+) (?P<action>.+)|API (?P<endpoint>[^ ]+) took (?P<duration>\d+)ms|(?P<err_msg>ERROR .+)|(?P<warn_msg>WARN .+)')
    match = log_pattern.match(line)

    if match:
        return match.groupdict()
    return {}


def extract_data(log_file: str) -> tuple:
    """Extract log data from the specified log file and return a tuple of error list, active sessions, and API calls."""
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    dt = parsed_line['date']
                    if parsed_line['level'] == 'ERROR':
                        d_list.append({"d": dt, "t": "ERR", "m": parsed_line['err_msg']})
                    elif parsed_line['action']:
                        uid = parsed_line['uid']
                        action = parsed_line['action']
                        if "logged in" in action:
                            sessions[uid] = dt
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                        d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                    elif parsed_line['endpoint']:
                        endpoint = parsed_line['endpoint']
                        dur = int(parsed_line['duration']) if parsed_line['duration'] else 0
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                    elif parsed_line['warn_msg']:
                        d_list.append({"d": dt, "t": "WARN", "m": parsed_line['warn_msg']})

    return d_list, sessions, api_calls


def load_to_db(data: list, api_calls: list, db_cfg: dict) -> None:
    """Load log processing results into the SQLite database."""
    conn = sqlite3.connect(db_cfg['DB_PATH'])
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    error_count = {}  
    for entry in data:
        if entry['t'] == 'ERR':
            msg = entry['m']
            error_count[msg] = error_count.get(msg, 0) + 1

    for msg, count in error_count.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), ep, avg))

    conn.commit()
    conn.close()


def generate_report(data: list, api_calls: list, sessions: dict) -> None:
    """Generate an HTML report from the processed log data."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    error_count = {}
    for entry in data:
        if entry['t'] == 'ERR':
            msg = entry['m']
            error_count[msg] = error_count.get(msg, 0) + 1
    for err_msg, count in error_count.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['ms'])
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{avg:.1f}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open("report.html", "w") as f:
        f.write(out)


if __name__ == '__main__':
    config = get_env_variables()
    log_data, active_sessions, api_calls = extract_data(config['LOG_FILE'])
    load_to_db(log_data, api_calls, config)
    generate_report(log_data, api_calls, active_sessions)
    print("Job finished at " + str(datetime.datetime.now()))
