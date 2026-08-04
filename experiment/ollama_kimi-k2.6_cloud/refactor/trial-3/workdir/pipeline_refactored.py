import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


def get_config() -> Dict[str, str]:
    """Load application configuration from environment variables."""
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


def extract_logs(log_file: str) -> Dict[str, Any]:
    """Extract raw events from the server log file.

    Returns:
        A dictionary with keys:
        - events: list of parsed log events
        - sessions: dict of active user IDs to login timestamps
        - api_calls: list of API call latency records
    """
    events: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}
    api_calls: List[Dict[str, Any]] = []

    log_path = Path(log_file)
    if not log_path.exists():
        return {"events": events, "sessions": sessions, "api_calls": api_calls}

    base_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (\w+) (.*)$")
    user_pattern = re.compile(r"^User (\d+) (.+)$")
    api_pattern = re.compile(r"^API (\S+) took (\d+)ms$")

    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = base_pattern.match(line)
            if not match:
                continue

            dt = f"{match.group(1)} {match.group(2)}"
            level = match.group(3)
            rest = match.group(4)

            if level == "ERROR":
                events.append({"dt": dt, "type": "ERR", "message": rest})
                continue

            if level == "WARN":
                events.append({"dt": dt, "type": "WARN", "message": rest})
                continue

            if level == "INFO":
                user_match = user_pattern.match(rest)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2)
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        del sessions[uid]
                    events.append({"dt": dt, "type": "USR", "uid": uid, "action": action})
                    continue

                api_match = api_pattern.match(rest)
                if api_match:
                    endpoint = api_match.group(1)
                    duration = int(api_match.group(2))
                    api_calls.append({"dt": dt, "endpoint": endpoint, "ms": duration})
                    events.append({"dt": dt, "type": "API", "endpoint": endpoint, "ms": duration})

    return {"events": events, "sessions": sessions, "api_calls": api_calls}


def transform_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform extracted log events into aggregated metrics.

    Computes error frequency and per-endpoint API latency averages.
    """
    events: List[Dict[str, Any]] = raw_data.get("events", [])
    sessions: Dict[str, str] = raw_data.get("sessions", {})
    api_calls: List[Dict[str, Any]] = raw_data.get("api_calls", [])

    error_counts: Dict[str, int] = {}
    for event in events:
        if event.get("type") == "ERR":
            msg = event.get("message", "")
            error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call.get("endpoint", "")
        endpoint_stats.setdefault(ep, []).append(call.get("ms", 0))

    endpoint_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        endpoint_averages[ep] = sum(times) / len(times)

    return {
        "error_counts": error_counts,
        "endpoint_averages": endpoint_averages,
        "active_sessions": len(sessions),
    }


def generate_report_html(data: Dict[str, Any]) -> str:
    """Generate the HTML report string from transformed metrics."""
    error_counts: Dict[str, int] = data.get("error_counts", {})
    endpoint_averages: Dict[str, float] = data.get("endpoint_averages", {})
    active_sessions: int = data.get("active_sessions", 0)

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


def load_data(data: Dict[str, Any], db_path: str) -> None:
    """Load metrics into the SQLite database and write the HTML report.

    Args:
        data: Transformed metrics dictionary.
        db_path: Path to the SQLite database file.
    """
    error_counts: Dict[str, int] = data.get("error_counts", {})
    endpoint_averages: Dict[str, float] = data.get("endpoint_averages", {})

    conn = sqlite3.connect(db_path)
    try:
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

        for ep, avg in endpoint_averages.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()

    html = generate_report_html(data)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)


def main() -> None:
    """Orchestrate the Extract-Transform-Load pipeline."""
    config = get_config()
    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    raw = extract_logs(config["log_file"])
    transformed = transform_data(raw)
    load_data(transformed, config["db_path"])

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_path = os.getenv("LOG_FILE", "server.log")
    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
