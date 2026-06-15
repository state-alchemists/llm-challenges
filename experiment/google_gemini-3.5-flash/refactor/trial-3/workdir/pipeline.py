import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration Constants sourced from Environment Variables with original defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
REPORT_FILE: str = os.getenv("REPORT_FILE", "report.html")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# Regular Expression Patterns for Log Line Parsing
# Format: TIMESTAMP TIMESTAMP LEVEL MESSAGE
LOG_PATTERN: re.Pattern = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+(.*)$"
)

# Parse "User <uid> <action>" pattern in INFO log messages
USER_PATTERN: re.Pattern = re.compile(r"^User\s+(\S+)\s+(.*)$")

# Parse "API <endpoint> took <duration>ms" pattern in INFO log messages
API_PATTERN: re.Pattern = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


def extract_logs(
    log_file_path: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """
    Extract raw log data from the specified log file using regular expressions.

    Args:
        log_file_path: The file path to the server log.

    Returns:
        A tuple of (d_list, sessions, api_calls) where:
        - d_list: Raw error, warning, and user action entries.
        - sessions: Currently active user sessions mapping user ID to login timestamp.
        - api_calls: Extracted raw api call metrics.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return d_list, sessions, api_calls

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_PATTERN.match(line.strip())
            if not match:
                continue

            dt = match.group(1)
            lvl = match.group(2)
            msg = match.group(3)

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": msg})

            elif lvl == "INFO":
                user_match = USER_PATTERN.match(msg)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})

                elif "API" in msg:
                    api_match = API_PATTERN.match(msg)
                    if api_match:
                        endpoint = api_match.group(1)
                        dur_str = api_match.group(2)
                        dur = int(dur_str) if dur_str else 0
                        api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})

            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": msg})

    return d_list, sessions, api_calls


def transform_errors(d_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Transform raw log entries to count occurrences of each error message.

    Args:
        d_list: List of raw parsed log entries.

    Returns:
        A dictionary mapping each error message to its total occurrence count.
    """
    error_counts: Dict[str, int] = {}
    for entry in d_list:
        if entry.get("t") == "ERR":
            msg = entry.get("m", "")
            error_counts[msg] = error_counts.get(msg, 0) + 1
    return error_counts


def transform_api_metrics(api_calls: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Transform raw API calls to compute the average latency for each endpoint.

    Args:
        api_calls: List of raw api call latency records.

    Returns:
        A dictionary mapping each API endpoint to its average duration in ms.
    """
    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        if times:
            api_averages[ep] = sum(times) / len(times)
        else:
            api_averages[ep] = 0.0
    return api_averages


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """
    Load the transformed metrics securely into the SQLite database.
    Uses parameterized queries to completely prevent SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Aggregated error counts to store.
        api_averages: Aggregated average API latencies to store.
        db_host: Database hostname (used for connection log message).
        db_port: Database port number (used for connection log message).
        db_user: Database user username (used for connection log message).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            # Parameters (?) fully prevent SQL injection
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (now_str, msg, count),
            )

        for ep, avg in api_averages.items():
            # Parameters (?) fully prevent SQL injection
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_to_html_report(
    report_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    active_sessions_count: int,
) -> None:
    """
    Generate and save the HTML performance and health report.

    Args:
        report_path: Output file path for the HTML report.
        error_counts: Dict of error message frequencies.
        api_averages: Dict of average api endpoint latencies.
        active_sessions_count: Total count of active user sessions.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions_count} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def proc_data() -> None:
    """
    Main orchestrator function for the ETL pipeline.
    """
    # 1. EXTRACT
    d_list, sessions, api_calls = extract_logs(LOG_FILE)

    # 2. TRANSFORM
    error_counts = transform_errors(d_list)
    api_averages = transform_api_metrics(api_calls)
    active_sessions_count = len(sessions)

    # 3. LOAD
    load_to_database(
        DB_PATH,
        error_counts,
        api_averages,
        DB_HOST,
        DB_PORT,
        DB_USER,
    )
    load_to_html_report(
        REPORT_FILE,
        error_counts,
        api_averages,
        active_sessions_count,
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    proc_data()
