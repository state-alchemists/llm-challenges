import datetime
import os
import sqlite3
import re
from typing import Dict, Any, Optional, List, Tuple

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")

# Regex patterns for log parsing
ERROR_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$")
INFO_USER_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\d+) (.*)$")
INFO_API_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$")
WARN_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$")

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex and returns a dictionary of its components.
    :param line: A single log line string.
    :return: A dictionary containing parsed log data, or None if the line doesn't match known patterns.
    """
    if (match := ERROR_PATTERN.match(line)):
        return {"d": match.group(1), "t": "ERR", "m": match.group(2).strip()}
    elif (match := INFO_USER_PATTERN.match(line)):
        uid = match.group(2)
        action = match.group(3).strip()
        return {"d": match.group(1), "t": "USR", "u": uid, "a": action}
    elif (match := INFO_API_PATTERN.match(line)):
        return {"d": match.group(1), "endpoint": match.group(2), "ms": int(match.group(3))}
    elif (match := WARN_PATTERN.match(line)):
        return {"d": match.group(1), "t": "WARN", "m": match.group(2).strip()}
    return None

def extract_log_data(log_file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Reads the log file, parses each line, and extracts error, session, and API call data.
    :param log_file_path: Path to the server log file.
    :return: A tuple containing lists of parsed errors, active sessions, and API calls.
    """
    d_list = []
    sessions = {}
    api_calls = []

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                parsed_line = parse_log_line(line)
                if parsed_line:
                    if parsed_line.get("t") == "ERR":
                        d_list.append(parsed_line)
                    elif parsed_line.get("t") == "USR":
                        uid = parsed_line["u"]
                        action = parsed_line["a"]
                        dt = parsed_line["d"]
                        if "logged in" in action:
                            sessions[uid] = dt
                        elif "logged out" in action and uid in sessions:
                            sessions.pop(uid)
                        d_list.append(parsed_line)
                    elif "endpoint" in parsed_line:  # API calls have "endpoint" key
                        api_calls.append(parsed_line)
                    elif parsed_line.get("t") == "WARN":
                        d_list.append(parsed_line)
    return d_list, sessions, api_calls

def transform_data(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms extracted log data into error summaries and API endpoint statistics.
    :param d_list: List of all parsed log entries.
    :param api_calls: List of parsed API call entries.
    :return: A tuple containing a dictionary of error message counts and a dictionary
             of API endpoint latencies (list of ms values).
    """
    error_summary = {}
    for x in d_list:
        if x.get("t") == "ERR":
            msg = x["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])
    
    return error_summary, endpoint_stats

def load_data_to_db(
    db_path: str,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """
    Loads processed data into an SQLite database.
    :param db_path: Path to the SQLite database file.
    :param error_summary: Dictionary of error message counts.
    :param endpoint_stats: Dictionary of API endpoint latencies.
    """
    print(f"Connecting to database {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )

    conn.commit()
    conn.close()
    print("Data loaded to database successfully.")

def generate_html_report(
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report from the processed data.
    :param error_summary: Dictionary of error message counts.
    :param endpoint_stats: Dictionary of API endpoint latencies.
    :param active_sessions_count: Number of currently active user sessions.
    :param output_file: The name of the HTML file to generate.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border=\'1\'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")


def main():
    """
    Main function to orchestrate log processing, data transformation, database loading,
    and HTML report generation.
    """
    print(f"Processing log file: {LOG_FILE}...")
    d_list, sessions, api_calls = extract_log_data(LOG_FILE)
    
    error_summary, endpoint_stats = transform_data(d_list, api_calls)

    load_data_to_db(DB_PATH, error_summary, endpoint_stats)

    generate_html_report(error_summary, endpoint_stats, len(sessions))
    
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Create a dummy log file if it doesn't exist for demonstration
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
