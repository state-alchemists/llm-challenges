"""Refactored log pipeline with ETL pattern, env-var config, and parameterized SQL."""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


def get_config() -> Dict[str, str]:
    """Load runtime configuration from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


# Regex patterns for parsing log lines.
LOG_LINE_RE = re.compile(r"^(\S+ \S+) (\w+) (.*)$")
USER_RE = re.compile(r"User (\d+) (.+)")
API_RE = re.compile(r"API (\S+)(?: took (\d+)ms)?")


def extract_log_events(
    log_path: str,
) -> Tuple[List[Dict[str, str]], Dict[str, str], List[Dict[str, str]]]:
    """Parse the server log into error events, active sessions, and API calls."""
    errors: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, str]] = []

    if not os.path.exists(log_path):
        return errors, sessions, api_calls

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            dt, level, payload = match.groups()

            if level == "ERROR":
                errors.append({"dt": dt, "message": payload})

            elif level == "INFO":
                user_match = USER_RE.search(payload)
                if user_match:
                    uid, action = user_match.groups()
                    if action == "logged in":
                        sessions[uid] = dt
                    elif action == "logged out" and uid in sessions:
                        sessions.pop(uid)
                    continue

                api_match = API_RE.search(payload)
                if api_match:
                    endpoint, duration = api_match.groups()
                    api_calls.append(
                        {"dt": dt, "endpoint": endpoint, "ms": duration or "0"}
                    )

    return errors, sessions, api_calls


def transform_metrics(
    errors: List[Dict[str, str]],
    api_calls: List[Dict[str, str]],
) -> Tuple[Dict[str, int], Dict[str, float]]:
    """Aggregate extracted events into error counts and API latency averages."""
    error_counts: Dict[str, int] = {}
    for entry in errors:
        msg = entry["message"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        endpoint = call["endpoint"]
        ms = int(call["ms"])
        endpoint_stats[endpoint].append(ms)

    endpoint_avgs: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        endpoint_avgs[ep] = sum(times) / len(times)

    return error_counts, endpoint_avgs


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_avgs: Dict[str, float],
    config: Dict[str, str],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries."""
    print(f"Connecting to {config['db_host']}:{config['db_port']} as {config['db_user']} ...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in endpoint_avgs.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    output_path: str,
    error_counts: Dict[str, int],
    endpoint_avgs: Dict[str, float],
    active_sessions: int,
) -> None:
    """Write an HTML report with error summary, API latency, and active sessions."""
    lines = [
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

    for ep, avg in endpoint_avgs.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = get_config()

    errors, sessions, api_calls = extract_log_events(config["log_file"])
    error_counts, endpoint_avgs = transform_metrics(errors, api_calls)
    load_to_database(
        config["db_path"], error_counts, endpoint_avgs, config
    )
    generate_report(
        "report.html", error_counts, endpoint_avgs, len(sessions)
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
