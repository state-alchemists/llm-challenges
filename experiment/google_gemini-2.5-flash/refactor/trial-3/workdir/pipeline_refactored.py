import datetime
import os
import re
import sqlite3
from typing import List, Dict, Any

DB_PATH = os.getenv("DB_PATH", "metrics.db")
LOG_FILE = os.getenv("LOG_FILE", "server.log")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


def extract_logs(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Reads a log file, parses each line using regex, and returns a list of structured log entries.

    Args:
        log_file_path: The path to the log file.

    Returns:
        A list of dictionaries, each representing a parsed log entry.
    """
    log_entries: List[Dict[str, Any]] = []
    log_pattern = re.compile(r"^(\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}) (INFO|ERROR|WARN) (.*)$")
    user_info_pattern = re.compile(r"User (\d+) (.*)$")
    api_call_pattern = re.compile(r"API (/\S+) took (\d+)ms$")

    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as f:
            for line in f:
                match = log_pattern.match(line)
                if match:
                    dt, level, message = match.groups()
                    entry: Dict[str, Any] = {"timestamp": dt, "level": level, "message": message.strip()}

                    if level == "INFO":
                        user_match = user_info_pattern.match(message)
                        if user_match:
                            uid, action = user_match.groups()
                            entry.update({"type": "USR", "user_id": uid, "action": action.strip()})
                        else:
                            api_match = api_call_pattern.match(message)
                            if api_match:
                                endpoint, duration = api_match.groups()
                                entry.update({"type": "API", "endpoint": endpoint, "duration_ms": int(duration)})
                            else:
                                # Generic INFO message if not user or API
                                entry.update({"type": "INFO"})
                    elif level == "ERROR":
                        entry.update({"type": "ERR"})
                    elif level == "WARN":
                        entry.update({"type": "WARN"})

                    log_entries.append(entry)
    return log_entries


def transform_data(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transforms raw log entries into aggregated data for reporting.

    Args:
        log_entries: A list of parsed log entries.

    Returns:
        A dictionary containing processed data: error summary, API latency statistics,
        and active session count.
    """
    error_summary: Dict[str, int] = {}
    api_latency: Dict[str, List[int]] = {}
    active_sessions: Dict[str, str] = {}

    for entry in log_entries:
        if entry["level"] == "ERROR":
            message = entry["message"]
            error_summary[message] = error_summary.get(message, 0) + 1
        elif entry["type"] == "API":
            endpoint = entry["endpoint"]
            duration = entry["duration_ms"]
            api_latency.setdefault(endpoint, []).append(duration)
        elif entry["type"] == "USR":
            user_id = entry["user_id"]
            action = entry["action"]
            if "logged in" in action:
                active_sessions[user_id] = entry["timestamp"]
            elif "logged out" in action and user_id in active_sessions:
                active_sessions.pop(user_id)

    # Calculate average API latency
    api_avg_latency: Dict[str, float] = {
        ep: sum(times) / len(times) for ep, times in api_latency.items()
    }

    return {
        "error_summary": error_summary,
        "api_avg_latency": api_avg_latency,
        "active_session_count": len(active_sessions),
    }


def load_data(
    error_summary: Dict[str, int], api_avg_latency: Dict[str, float], db_path: str
) -> None:
    """
    Connects to the database and loads the processed error and API latency data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_avg_latency: A dictionary of API endpoints and their average latencies.
        db_path: The path to the SQLite database file.
    """
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    for msg, count in error_summary.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), msg, count),
        )

    for ep, avg in api_avg_latency.items():
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (datetime.datetime.now().isoformat(), ep, avg),
        )

    conn.commit()
    conn.close()
    print("Data loaded to database.")


def generate_report(
    error_summary: Dict[str, int], api_avg_latency: Dict[str, float], active_session_count: int
) -> None:
    """
    Generates an HTML report from the processed data.

    Args:
        error_summary: A dictionary of error messages and their counts.
        api_avg_latency: A dictionary of API endpoints and their average latencies.
        active_session_count: The number of currently active user sessions.
    """
    out = """<html>
<head><title>System Report</title></head>
<body>
<h1>Error Summary</h1>
<ul>
"""
    for err_msg, count in error_summary.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += """</ul>

<h2>API Latency</h2>
<table border='1'>
<tr><th>Endpoint</th><th>Avg (ms)</th></tr>
"""
    for ep, avg in api_avg_latency.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += """</table>

<h2>Active Sessions</h2>
<p>{active_session_count} user(s) currently active</p>
</body>
</html>"""

    with open("report.html", "w") as f:
        f.write(out)
    print("Report generated: report.html")


def main():
    """
    Orchestrates the log processing, data transformation, loading, and report generation.
    """
    # Extract
    log_entries = extract_logs(LOG_FILE)

    # Transform
    processed_data = transform_data(log_entries)

    # Load
    load_data(
        processed_data["error_summary"],
        processed_data["api_avg_latency"],
        DB_PATH,
    )

    # Report
    generate_report(
        processed_data["error_summary"],
        processed_data["api_avg_latency"],
        processed_data["active_session_count"],
    )

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
