"""ETL pipeline that parses server logs and generates an HTML report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3

LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)

USER_RE = re.compile(r"^User (?P<uid>\S+) (?P<action>.*)$")

API_RE = re.compile(
    r"^API (?P<endpoint>\S+)(?: took (?P<duration>\d+)ms)?$"
)


def get_config() -> dict[str, str]:
    """Return configuration values read from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", ""),
    }


def extract_events(log_path: str) -> tuple[list[dict[str, str]], dict[str, str], list[dict[str, str | int]]]:
    """Extract events from the server log file.

    Args:
        log_path: Path to the server log file.

    Returns:
        A tuple containing:
            - List of error events (timestamp and message).
            - Dictionary of active sessions (user_id -> timestamp).
            - List of API call events.
    """
    errors: list[dict[str, str]] = []
    sessions: dict[str, str] = {}
    api_calls: list[dict[str, str | int]] = []

    if not os.path.exists(log_path):
        return errors, sessions, api_calls

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            message = match.group("message")

            if level == "ERROR":
                errors.append({"timestamp": timestamp, "message": message})
            elif level == "INFO":
                user_match = USER_RE.match(message)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action")
                    if action == "logged in":
                        sessions[uid] = timestamp
                    elif action == "logged out" and uid in sessions:
                        sessions.pop(uid)
                else:
                    api_match = API_RE.match(message)
                    if api_match:
                        endpoint = api_match.group("endpoint")
                        duration_raw = api_match.group("duration")
                        duration = int(duration_raw) if duration_raw else 0
                        api_calls.append({
                            "timestamp": timestamp,
                            "endpoint": endpoint,
                            "ms": duration,
                        })
            elif level == "WARN":
                # Preserved for parity with original pipeline behaviour.
                pass

    return errors, sessions, api_calls


def transform_metrics(
    errors: list[dict[str, str]],
    api_calls: list[dict[str, str | int]],
) -> tuple[dict[str, int], dict[str, float]]:
    """Transform raw events into aggregated metrics.

    Args:
        errors: List of error events.
        api_calls: List of API call events.

    Returns:
        A tuple containing:
            - Dictionary mapping error message to occurrence count.
            - Dictionary mapping endpoint to average latency in milliseconds.
    """
    error_counts: dict[str, int] = {}
    for event in errors:
        msg = event["message"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in api_calls:
        ep = str(call["endpoint"])
        endpoint_times.setdefault(ep, []).append(int(call["ms"]))

    endpoint_averages: dict[str, float] = {}
    for ep, times in endpoint_times.items():
        endpoint_averages[ep] = sum(times) / len(times)

    return error_counts, endpoint_averages


def load_report(
    db_path: str,
    error_counts: dict[str, int],
    endpoint_averages: dict[str, float],
    active_sessions: int,
) -> None:
    """Load aggregated metrics into the database and write the HTML report.

    Args:
        db_path: Path to the SQLite database.
        error_counts: Aggregated error counts.
        endpoint_averages: Aggregated API latencies.
        active_sessions: Number of currently active sessions.
    """
    print(f"Connecting to database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in endpoint_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    html = _generate_html(error_counts, endpoint_averages, active_sessions)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Job finished at {datetime.datetime.now()}")


def _generate_html(
    error_counts: dict[str, int],
    endpoint_averages: dict[str, float],
    active_sessions: int,
) -> str:
    """Generate the HTML report string.

    Args:
        error_counts: Aggregated error counts.
        endpoint_averages: Aggregated API latencies.
        active_sessions: Number of currently active sessions.

    Returns:
        HTML report content.
    """
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, avg in endpoint_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def main() -> None:
    """Run the ETL pipeline."""
    config = get_config()
    errors, sessions, api_calls = extract_events(config["log_file"])
    error_counts, endpoint_averages = transform_metrics(errors, api_calls)
    load_report(
        config["db_path"],
        error_counts,
        endpoint_averages,
        len(sessions),
    )


if __name__ == "__main__":
    log_file = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
