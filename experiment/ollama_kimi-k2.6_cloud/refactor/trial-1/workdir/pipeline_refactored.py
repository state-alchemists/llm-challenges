import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


# Regex patterns for robust log line parsing
_LOG_BASE_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>ERROR|INFO|WARN) "
    r"(?P<message>.+)$"
)
_USER_RE = re.compile(r"^User (?P<user_id>\d+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$")


def get_config() -> Dict[str, str]:
    """Load configuration from environment variables."""
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": os.environ.get("DB_PORT", "5432"),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


def extract(
    log_file: str,
) -> Tuple[Dict[str, int], Dict[str, str], Dict[str, List[int]]]:
    """Extract raw events from the server log file.

    Returns:
        A tuple of (error_counts, active_sessions, endpoint_latencies).
    """
    error_counts: Dict[str, int] = {}
    active_sessions: Dict[str, str] = {}
    endpoint_latencies: Dict[str, List[int]] = defaultdict(list)

    if not os.path.exists(log_file):
        return error_counts, active_sessions, dict(endpoint_latencies)

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            base_match = _LOG_BASE_RE.match(line)
            if not base_match:
                continue

            dt = base_match.group("dt")
            level = base_match.group("level")
            message = base_match.group("message")

            if level == "ERROR":
                error_counts[message] = error_counts.get(message, 0) + 1
            elif level == "INFO":
                user_match = _USER_RE.match(message)
                if user_match:
                    user_id = user_match.group("user_id")
                    action = user_match.group("action")
                    if "logged in" in action:
                        active_sessions[user_id] = dt
                    elif "logged out" in action and user_id in active_sessions:
                        active_sessions.pop(user_id)
                    continue

                api_match = _API_RE.match(message)
                if api_match:
                    endpoint = api_match.group("endpoint")
                    duration_str = api_match.group("duration")
                    duration = int(duration_str) if duration_str else 0
                    endpoint_latencies[endpoint].append(duration)
            elif level == "WARN":
                # Original script collected WARN entries but never persisted
                # them to the database or report. We preserve parity by
                # parsing but not storing.
                pass

    return error_counts, active_sessions, dict(endpoint_latencies)


def transform(
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
) -> Tuple[List[Tuple[str, str, int]], List[Tuple[str, str, float]]]:
    """Transform extracted raw data into load-ready aggregates.

    Returns:
        A tuple of (error_records, api_metric_records).
    """
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    error_records: List[Tuple[str, str, int]] = [
        (timestamp, msg, count) for msg, count in error_counts.items()
    ]

    api_records: List[Tuple[str, str, float]] = []
    for endpoint, times in endpoint_latencies.items():
        avg_ms = sum(times) / len(times)
        api_records.append((timestamp, endpoint, avg_ms))

    return error_records, api_records


def load(
    db_path: str,
    error_records: List[Tuple[str, str, int]],
    api_records: List[Tuple[str, str, float]],
    db_host: str,
    db_port: str,
    db_user: str,
) -> None:
    """Load transformed aggregates into SQLite.

    Args:
        db_path: Path to the SQLite database file.
        error_records: Tuples of (timestamp, message, count).
        api_records: Tuples of (timestamp, endpoint, avg_ms).
        db_host: Database host (informational only for SQLite).
        db_port: Database port (informational only for SQLite).
        db_user: Database user (informational only for SQLite).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    cursor.executemany(
        "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
        error_records,
    )
    cursor.executemany(
        "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
        api_records,
    )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    endpoint_latencies: Dict[str, List[int]],
    active_sessions: Dict[str, str],
    output_path: str = "report.html",
) -> None:
    """Generate the HTML report from transformed data.

    Args:
        error_counts: Mapping of error message to occurrence count.
        endpoint_latencies: Mapping of endpoint to list of latencies in ms.
        active_sessions: Mapping of active user_id to login timestamp.
        output_path: Destination file path for the HTML report.
    """
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, times in endpoint_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Orchestrate Extract -> Transform -> Load and report generation."""
    config = get_config()

    log_file = config["log_file"]
    db_path = config["db_path"]

    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    error_counts, active_sessions, endpoint_latencies = extract(log_file)
    error_records, api_records = transform(error_counts, endpoint_latencies)
    load(
        db_path,
        error_records,
        api_records,
        config["db_host"],
        config["db_port"],
        config["db_user"],
    )
    generate_report(error_counts, endpoint_latencies, active_sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
