import datetime
import os
import re
import sqlite3
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

@dataclass
class Config:
    """Configuration class to hold settings loaded from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def load_from_env(cls) -> "Config":
        """Loads configuration from environment variables."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
        )

def extract_log_data(log_file: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extracts data from the log file using regular expressions.

    Args:
        log_file: The path to the server log file.

    Returns:
        A tuple containing:
        - A list of parsed log entries (errors, warnings, user actions).
        - A dictionary of active user sessions.
        - A list of API call details.
    """
    parsed_entries: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    # Regex patterns for different log types
    error_pattern = re.compile(r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<message>.*)$")
    warn_pattern = re.compile(r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<message>.*)$")
    user_pattern = re.compile(r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (?P<user_id>\S+) (?P<action>.*)$")
    api_pattern = re.compile(r"^(?P<datetime>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")

    if not os.path.exists(log_file):
        print(f"Log file not found: {log_file}")
        return parsed_entries, sessions, api_calls

    with open(log_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            error_match = error_pattern.match(line)
            if error_match:
                parsed_entries.append({"d": error_match.group("datetime"), "t": "ERR", "m": error_match.group("message")})
                continue

            warn_match = warn_pattern.match(line)
            if warn_match:
                parsed_entries.append({"d": warn_match.group("datetime"), "t": "WARN", "m": warn_match.group("message")})
                continue

            user_match = user_pattern.match(line)
            if user_match:
                uid = user_match.group("user_id")
                action = user_match.group("action")
                dt = user_match.group("datetime")
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
                parsed_entries.append({"d": dt, "t": "USR", "u": uid, "a": action})
                continue

            api_match = api_pattern.match(line)
            if api_match:
                api_calls.append({
                    "d": api_match.group("datetime"),
                    "endpoint": api_match.group("endpoint"),
                    "ms": int(api_match.group("duration"))
                })
                continue

    return parsed_entries, sessions, api_calls

def transform_data(
    parsed_entries: List[Dict[str, Any]],
    api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """
    Transforms raw log entries into structured data for reporting.

    Args:
        parsed_entries: List of parsed log entries.
        api_calls: List of API call details.

    Returns:
        A tuple containing:
        - A dictionary of error messages and their counts.
        - A dictionary of API endpoints and a list of their latencies.
    """
    error_summary: Dict[str, int] = {}
    for entry in parsed_entries:
        if entry["t"] == "ERR":
            msg = entry["m"]
            error_summary[msg] = error_summary.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    return error_summary, endpoint_stats

def load_data_to_db(
    config: Config,
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]]
) -> None:
    """
    Loads transformed data into the SQLite database.

    Args:
        config: The configuration object containing DB path.
        error_summary: A dictionary of error messages and their counts.
        endpoint_stats: A dictionary of API endpoints and their latencies.
    """
    print(f"Connecting to database at {config.db_path}...")
    conn = sqlite3.connect(config.db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count)
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        c.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg)
        )

    conn.commit()
    conn.close()
    print("Data loaded to database.")

def generate_report(
    error_summary: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions_count: int,
    output_file: str = "report.html"
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        endpoint_stats: A dictionary of API endpoints and their latencies.
        active_sessions_count: The number of active user sessions.
        output_file: The path to the output HTML report file.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\\n<table border='1'>\\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times) if times else 0.0
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_file, "w") as f:
        f.write(out)
    print(f"Report generated: {output_file}")

def main():
    """Main function to run the data processing pipeline."""
    config = Config.load_from_env()

    # Ensure a log file exists for demonstration if not provided
    if not os.path.exists(config.log_file):
        print(f"Creating a sample log file: {config.log_file}")
        with open(config.log_file, "w") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
            f.write("2024-01-01 12:15:00 INFO API /products took 100ms\n")
            f.write("2024-01-01 12:16:00 INFO API /products took 50ms\n")


    parsed_entries, sessions, api_calls = extract_log_data(config.log_file)
    error_summary, endpoint_stats = transform_data(parsed_entries, api_calls)
    load_data_to_db(config, error_summary, endpoint_stats)
    generate_report(error_summary, endpoint_stats, len(sessions))

    print(f"Job finished at {datetime.datetime.now()}")

if __name__ == "__main__":
    main()
