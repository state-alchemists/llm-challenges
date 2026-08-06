import os
import sqlite3
import datetime
import re
from typing import List, Dict, Any, Optional, Tuple

class Config:
    """
    Configuration class to hold settings loaded from environment variables.
    """
    db_path: str
    log_file_path: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    def __init__(self):
        self.db_path = os.getenv("DB_PATH", "metrics.db")
        self.log_file_path = os.getenv("LOG_FILE", "server.log")
        # These are kept for completeness based on original code, but sqlite3
        # does not use host/port/user/pass for file-based databases.
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", "5432"))
        self.db_user = os.getenv("DB_USER", "admin")
        self.db_pass = os.getenv("DB_PASS", "password123")

def load_config() -> Config:
    """Loads configuration from environment variables."""
    return Config()

# Regex patterns for different log line types
# Backslashes are doubled for the string literal passed to Write to be correctly interpreted as a single backslash in the Python code
LOG_PATTERN_ERROR = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)")
LOG_PATTERN_INFO_USER = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\w+) (.*)")
LOG_PATTERN_INFO_API = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (/[\w/]+) took (\d+)ms")
LOG_PATTERN_WARN = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)")


def read_log_file(log_file_path: str) -> List[str]:
    """
    Reads the log file line by line.
    Args:
        log_file_path: Path to the log file.
    Returns:
        A list of log file lines.
    """
    if not os.path.exists(log_file_path):
        print(f"Log file not found at {log_file_path}")
        return []
    with open(log_file_path, "r") as f:
        return f.readlines()

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single log line using regex.
    Args:
        line: A single log line string.
    Returns:
        A dictionary containing parsed log data, or None if the line doesn't match a known pattern.
    """
    if match := LOG_PATTERN_ERROR.match(line):
        return {"d": match.group(1), "t": "ERR", "m": match.group(2).strip()}
    elif match := LOG_PATTERN_INFO_USER.match(line):
        uid, action = match.group(2), match.group(3).strip()
        return {"d": match.group(1), "t": "USR", "u": uid, "a": action}
    elif match := LOG_PATTERN_INFO_API.match(line):
        return {"d": match.group(1), "t": "API", "endpoint": match.group(2), "ms": int(match.group(3))}
    elif match := LOG_PATTERN_WARN.match(line):
        return {"d": match.group(1), "t": "WARN", "m": match.group(2).strip()}
    return None

def extract_log_data(log_lines: List[str]) -> Tuple[List[Dict], List[Dict], Dict[str, str]]:
    """
    Extracts structured data from a list of log lines.
    Args:
        log_lines: List of raw log strings.
    Returns:
        A tuple containing:
        - List of dictionaries for error/warning/user actions.
        - List of dictionaries for API calls.
        - Dictionary of active user sessions (uid -> login_timestamp).
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    for line in log_lines:
        parsed_data = parse_log_line(line)
        if not parsed_data:
            continue

        record_type = parsed_data.get("t")
        if record_type in ["ERR", "WARN", "USR"]:
            d_list.append(parsed_data)
            if record_type == "USR":
                uid = parsed_data["u"]
                action = parsed_data["a"]
                if "logged in" in action:
                    sessions[uid] = parsed_data["d"]
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
        elif record_type == "API":
            api_calls.append(parsed_data)
    return d_list, api_calls, sessions


def analyze_errors(extracted_data: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Counts occurrences of each error message.
    Args:
        extracted_data: List of parsed log data.
    Returns:
        A dictionary with error messages as keys and their counts as values.
    """
    error_summary: Dict[str, int] = {}
    for record in extracted_data:
        if record.get("t") == "ERR":
            msg = record["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1
    return error_summary

def analyze_api_latency(api_calls: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculates the average API latency for each endpoint.
    Args:
        api_calls: List of dictionaries representing API calls.
    Returns:
        A dictionary with API endpoints as keys and their average latencies (ms) as values.
    """
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        endpoint_stats.setdefault(call["endpoint"], []).append(call["ms"])

    api_latency_stats: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in endpoint_stats.items()
    }
    return api_latency_stats

def get_active_sessions_count(sessions: Dict[str, str]) -> int:
    """
    Returns the count of currently active user sessions.
    Args:
        sessions: Dictionary of active user sessions.
    Returns:
        The number of active sessions.
    """
    return len(sessions)


def setup_database(db_path: str) -> sqlite3.Connection:
    """
    Connects to the SQLite database and creates necessary tables.
    Args:
        db_path: Path to the SQLite database file.
    Returns:
        A sqlite3 connection object.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
    conn.commit()
    return conn

def insert_errors(conn: sqlite3.Connection, errors_summary: Dict[str, int]) -> None:
    """
    Inserts error summary data into the 'errors' table using parameterized queries.
    Args:
        conn: SQLite database connection.
        errors_summary: Dictionary of error messages and their counts.
    """
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for msg, count in errors_summary.items():
        # Parameterized query to prevent SQL injection
        c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))
    conn.commit()

def insert_api_metrics(conn: sqlite3.Connection, api_latency_stats: Dict[str, float]) -> None:
    """
    Inserts API latency metrics into the 'api_metrics' table using parameterized queries.
    Args:
        conn: SQLite database connection.
        api_latency_stats: Dictionary of API endpoints and their average latencies.
    """
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ep, avg in api_latency_stats.items():
        # Parameterized query to prevent SQL injection
        c.execute("INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)", (now, ep, avg))
    conn.commit()

def generate_report(
    errors_summary: Dict[str, int],
    api_latency_stats: Dict[str, float],
    active_sessions_count: int
) -> str:
    """
    Generates the HTML report content.
    Args:
        errors_summary: Dictionary of error messages and their counts.
        api_latency_stats: Dictionary of API endpoints and their average latencies.
        active_sessions_count: Number of active user sessions.
    Returns:
        A string containing the full HTML report.
    """
    # Use triple-quoted f-string for multi-line HTML, handling newlines directly.
    # Curly braces within the f-string's literal parts must be doubled to be literal.
    report_html = f"""<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in errors_summary.items():
        report_html += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    report_html += f"""</ul>

<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, avg in api_latency_stats.items():
        report_html += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    report_html += f"""</table>

<h2>Active Sessions</h2>
<p>{active_sessions_count} user(s) currently active</p>
</body>
</html>"""
    return report_html

def write_report_to_file(report_content: str, output_path: str) -> None:
    """
    Writes the generated HTML report to a file.
    Args:
        report_content: The HTML content string.
        output_path: The file path to write the report to.
    """
    with open(output_path, "w") as f:
        f.write(report_content)
    print(f"Report generated at {output_path}")


def main():
    """Main function to orchestrate the log processing and report generation."""
    config = load_config()
    print(f"Loading config: DB_PATH={config.db_path}, LOG_FILE={config.log_file_path}")

    # Ensure a dummy log file exists for demonstration if not present
    if not os.path.exists(config.log_file_path):
        print(f"Creating dummy log file at {config.log_file_path}")
        with open(config.log_file_path, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /products/view took 120ms\n")
            f.write("2024-01-01 12:16:00 INFO API /products/view took 80ms\n")
            f.write("2024-01-01 12:17:00 ERROR Network unreachable\n")


    # Extract
    log_lines = read_log_file(config.log_file_path)
    d_list, api_calls, sessions = extract_log_data(log_lines)

    # Transform
    errors_summary = analyze_errors(d_list)
    api_latency_stats = analyze_api_latency(api_calls)
    active_sessions_count = get_active_sessions_count(sessions)

    # Load to DB
    conn = setup_database(config.db_path)
    insert_errors(conn, errors_summary)
    insert_api_metrics(conn, api_latency_stats)
    conn.close()
    print(f"Data loaded to database: {config.db_path}")

    # Load to HTML report
    report_content = generate_report(errors_summary, api_latency_stats, active_sessions_count)
    write_report_to_file(report_content, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
