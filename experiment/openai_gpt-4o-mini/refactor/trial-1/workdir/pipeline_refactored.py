import os
import re
import datetime
import sqlite3

# Configuration constants
DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def parse_log_line(line: str) -> dict:
    """Parses a line from the log file and returns a structured entry."""
    match = re.match(r'(?P<date>\d+-\d+-\d+ \d+:\d+:\d+) (?P<level>[A-Z]*) (?P<details>.+)', line)
    if match:
        dt = match.group("date")
        lvl = match.group("level")
        details = match.group("details")
        return {
            "date": dt,
            "level": lvl,
            "details": details
        }
    return None


def process_logs():
    """Processes the server logs and returns a list of structured log entries."""
    log_entries = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                entry = parse_log_line(line)
                if entry:
                    log_entries.append(entry)
    return log_entries


def extract_error_summary(entries: list) -> dict:
    """Extracts error messages and their counts from log entries."""
    error_summary = {}
    for entry in entries:
        if entry["level"] == "ERROR":
            error_msg = entry["details"]
            error_summary[error_msg] = error_summary.get(error_msg, 0) + 1
    return error_summary


def extract_api_metrics(entries: list) -> dict:
    """Extracts API call metrics from log entries and returns a dictionary of API call latencies."""
    api_metrics = {}
    for entry in entries:
        if entry["level"] == "INFO" and "API" in entry["details"]:
            api_call = re.search(r'API (?P<endpoint>[^ ]+) took (?P<duration>\d+)ms', entry["details"])
            if api_call:
                endpoint = api_call.group("endpoint")
                duration = int(api_call.group("duration"))
                api_metrics.setdefault(endpoint, []).append(duration)
    return api_metrics


def persist_summary_to_db(error_summary: dict, api_metrics: dict):
    """Persists error summary and API metrics to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute("INSERT INTO errors VALUES (?, ?, ?)", (datetime.datetime.now(), msg, count))

    for endpoint, durations in api_metrics.items():
        avg_duration = sum(durations) / len(durations)
        c.execute("INSERT INTO api_metrics VALUES (?, ?, ?)", (datetime.datetime.now(), endpoint, avg_duration))

    conn.commit()
    conn.close()


def generate_report(error_summary: dict, api_metrics: dict, active_users: int) -> str:
    """Generates HTML report from error summary, API metrics, and active session count."""
    report = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    report += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        report += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    report += "</ul>\n"

    report += "<h2>API Latency</h2>\n<table border='1'>\n"
    report += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for endpoint, durations in api_metrics.items():
        avg_duration = sum(durations) / len(durations)
        report += f"<tr><td>{endpoint}</td><td>{round(avg_duration, 1)}</td></tr>\n"
    report += "</table>\n"

    report += f"<h2>Active Sessions</h2>\n<p>{active_users} user(s) currently active</p>\n"
    report += "</body>\n</html>"
    return report


def proc_data():
    """Main data processing function that coordinates the ETL pipeline."""
    log_entries = process_logs()
    error_summary = extract_error_summary(log_entries)
    api_metrics = extract_api_metrics(log_entries)
    active_users = len({entry['details'].split()[1] for entry in log_entries if "logged in" in entry['details']})
    persist_summary_to_db(error_summary, api_metrics)
    report_content = generate_report(error_summary, api_metrics, active_users)

    with open("report.html", "w") as f:
        f.write(report_content)

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