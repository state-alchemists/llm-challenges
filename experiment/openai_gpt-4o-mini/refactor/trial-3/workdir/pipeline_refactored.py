import datetime
import os
import re
import sqlite3

# Load environment variables
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """
    Parse a line from the log file.
    
    Args:
        line (str): A single line from the log file.
    
    Returns:
        dict: Parsed components of the log line.
    """
    pattern = re.compile(r'^(\S+ \S+) (\S+) (.*)$')
    match = pattern.match(line)
    if match:
        dt, level, message = match.groups()
        return {'dt': dt, 'level': level, 'message': message}
    return {}  # Return an empty dictionary if no match is found


def extract_log_entries():
    """
    Extract entries from the log file.
    
    Returns:
        list: A list of parsed log entries.
    """
    entries = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            for line in f:
                parsed = parse_log_line(line)
                if parsed:
                    entries.append(parsed)
    return entries


def process_log_entries(entries: list) -> tuple:
    """
    Process the log entries to extract relevant data.
    
    Args:
        entries (list): List of log entries.
    
    Returns:
        tuple: Contains error messages and API call metrics.
    """
    error_count = {}
    api_calls = []
    sessions = {}
    for entry in entries:
        dt = entry['dt']
        level = entry['level']
        message = entry['message']
        
        if level == "ERROR":
            error_count[message] = error_count.get(message, 0) + 1
        elif level == "INFO":
            if "User" in message:
                if "logged in" in message:
                    uid = message.split()[1]
                    sessions[uid] = dt
                elif "logged out" in message:
                    uid = message.split()[1]
                    sessions.pop(uid, None)
            elif "API" in message:
                parts = message.split()
                endpoint = parts[1]
                duration = int(parts[3].replace("took ", "").replace("ms", ""))
                api_calls.append({'endpoint': endpoint, 'duration': duration})
    return error_count, api_calls, sessions


def save_metrics_to_db(error_count: dict, api_calls: list):
    """
    Save the error and API call metrics to the database.
    
    Args:
        error_count (dict): Dictionary of error messages and counts.
        api_calls (list): List of API call metrics.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    current_dt = datetime.datetime.now()
    for message, count in error_count.items():
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (current_dt, message, count))

    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        endpoint_stats.setdefault(ep, []).append(call['duration'])

    for ep, durations in endpoint_stats.items():
        avg_duration = sum(durations) / len(durations)
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (current_dt, ep, avg_duration))

    conn.commit()
    conn.close()


def generate_report(error_count: dict, api_calls: list, sessions: dict):
    """
    Generate an HTML report based on the processed data.
    
    Args:
        error_count (dict): Dictionary of error messages and counts.
        api_calls (list): List of API call metrics.
        sessions (dict): Dictionary of active sessions.
    """
    report_content = "<html><head><title>System Report</title></head><body>"
    report_content += "<h1>Error Summary</h1><ul>"
    for msg, count in error_count.items():
        report_content += f"<li><b>{msg}</b>: {count} occurrences</li>"
    report_content += "</ul><h2>API Latency</h2><table border='1'><tr><th>Endpoint</th><th>Avg (ms)</th></tr>"
    endpoint_stats = {}
    for call in api_calls:
        ep = call['endpoint']
        duration = call['duration']
        endpoint_stats.setdefault(ep, []).append(duration)
    for ep, durations in endpoint_stats.items():
        avg_duration = sum(durations) / len(durations)
        report_content += f"<tr><td>{ep}</td><td>{round(avg_duration, 1)}</td></tr>"
    report_content += "</table><h2>Active Sessions</h2>"
    report_content += f"<p>{len(sessions)} user(s) currently active</p>"
    report_content += "</body></html>"

    with open("report.html", "w") as f:
        f.write(report_content)


def proc_data():
    """
    Main function to orchestrate the data processing.
    """
    log_entries = extract_log_entries()
    error_count, api_calls, sessions = process_log_entries(log_entries)
    save_metrics_to_db(error_count, api_calls)
    generate_report(error_count, api_calls, sessions)
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