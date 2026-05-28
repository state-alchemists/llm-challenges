import datetime
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

# Configuration using environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_data(
    log_file_path: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, Any]]]:
    """Extract and parse log entries from the specified log file path.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        A tuple containing:
            - d_list: List of parsed log dictionaries.
            - sessions: Dictionary tracking active user sessions.
            - api_calls: List of parsed API call metrics.
    """
    d_list: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    if not os.path.exists(log_file_path):
        return d_list, sessions, api_calls

    # Matches general format: timestamp level message
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$"
    )
    user_pattern = re.compile(r"User\s+(\S+)\s+(.+)$")
    api_pattern = re.compile(r"API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if not match:
                continue

            dt, lvl, message = match.groups()

            if lvl == "ERROR":
                d_list.append({"d": dt, "t": "ERR", "m": message.strip()})

            elif lvl == "INFO":
                user_match = user_pattern.search(message)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                    d_list.append({"d": dt, "t": "USR", "u": uid, "a": action})
                    continue

                api_match = api_pattern.search(message)
                if api_match:
                    endpoint = api_match.group(1)
                    dur_str = api_match.group(2)
                    dur = int(dur_str) if dur_str else 0
                    api_calls.append({"d": dt, "endpoint": endpoint, "ms": dur})
                    continue

            elif lvl == "WARN":
                d_list.append({"d": dt, "t": "WARN", "m": message.strip()})

    return d_list, sessions, api_calls


def transform_log_data(
    d_list: List[Dict[str, Any]], api_calls: List[Dict[str, Any]]
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """Transform extracted log data into aggregated metrics.

    Args:
        d_list: List of parsed log dictionaries.
        api_calls: List of parsed API call metrics.

    Returns:
        A tuple containing:
            - error_counts: Dict mapping error messages to occurrence counts.
            - api_averages: Dict mapping endpoints to average latency.
    """
    error_counts: Dict[str, int] = {}
    for entry in d_list:
        if entry.get("t") == "ERR":
            msg = entry["m"]
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_latencies: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_latencies.setdefault(ep, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for ep, times in endpoint_latencies.items():
        if times:
            api_averages[ep] = sum(times) / len(times)
        else:
            api_averages[ep] = 0.0

    return error_counts, api_averages


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
) -> None:
    """Load aggregated metrics into the SQLite database.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Dict of error messages and counts.
        api_averages: Dict of endpoints and average latencies.
    """
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now_str = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        c.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now_str, msg, count),
        )

    for ep, avg in api_averages.items():
        c.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now_str, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    api_averages: Dict[str, float],
    sessions: Dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Generate the HTML system report.

    Args:
        error_counts: Dict of error messages and counts.
        api_averages: Dict of endpoints and average latencies.
        sessions: Dict tracking active user sessions.
        output_path: Target path for the HTML report.
    """
    out_lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        out_lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    out_lines.append("</ul>")

    out_lines.extend(
        [
            "<h2>API Latency</h2>",
            "<table border='1'>",
            "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
        ]
    )

    for ep, avg in api_averages.items():
        out_lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    out_lines.append("</table>")

    out_lines.extend(
        [
            "<h2>Active Sessions</h2>",
            f"<p>{len(sessions)} user(s) currently active</p>",
            "</body>",
            "</html>",
        ]
    )

    out = "\n".join(out_lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution orchestrator of the ETL pipeline."""
    # 1. Extract
    d_list, sessions, api_calls = extract_log_data(LOG_FILE)

    # 2. Transform
    error_counts, api_averages = transform_log_data(d_list, api_calls)

    # 3. Load
    load_to_database(DB_PATH, error_counts, api_averages)

    # 4. Report
    generate_report(error_counts, api_averages, sessions, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_log:
            f_log.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_log.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_log.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_log.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_log.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
