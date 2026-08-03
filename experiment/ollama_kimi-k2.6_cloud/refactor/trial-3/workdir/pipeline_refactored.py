"""Log processing pipeline: Extract server logs, transform metrics, and load to DB + HTML report."""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (loaded from environment variables)
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")

# ---------------------------------------------------------------------------
# Regex patterns for log parsing
# ---------------------------------------------------------------------------

LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)

USER_ACTION_RE = re.compile(r"User (?P<uid>\S+) (?P<action>.+)")
API_CALL_RE = re.compile(r"API (?P<endpoint>\S+) took (?P<duration_ms>\d+)ms")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

type LogEntry = dict[str, str]


def get_config() -> dict[str, str | int]:
    """Return runtime configuration as a dictionary.

    All values are read from environment variables with sensible defaults.
    """
    return {
        "db_path": DB_PATH,
        "log_file": LOG_FILE,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_user": DB_USER,
        "db_pass": DB_PASS,
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract_logs(log_file: str) -> list[LogEntry]:
    """Parse *log_file* and return a list of structured log entries.

    Each entry contains at minimum ``timestamp``, ``level``, and ``message``.
    Additional fields are added depending on the log type (e.g. ``uid``,
    ``endpoint``, ``duration_ms``).
    """
    entries: list[LogEntry] = []
    path = Path(log_file)
    if not path.exists():
        return entries

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            timestamp = match.group("timestamp")
            level = match.group("level")
            message = match.group("message")

            entry: LogEntry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
            }

            if level == "ERROR":
                entry["type"] = "ERR"
            elif level == "WARN":
                entry["type"] = "WARN"
            elif level == "INFO" and "User" in message:
                user_match = USER_ACTION_RE.search(message)
                if user_match:
                    entry["type"] = "USR"
                    entry["uid"] = user_match.group("uid")
                    entry["action"] = user_match.group("action")
            elif level == "INFO" and "API" in message:
                api_match = API_CALL_RE.search(message)
                if api_match:
                    entry["type"] = "API"
                    entry["endpoint"] = api_match.group("endpoint")
                    entry["duration_ms"] = api_match.group("duration_ms")

            entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_log_entries(entries: list[LogEntry]) -> dict:
    """Aggregate extracted log entries into report-ready structures.

    Returns a dict with:
    - ``error_counts``: mapping of error message -> occurrence count
    - ``api_latencies``: mapping of endpoint -> list of durations (ms)
    - ``active_sessions``: mapping of user id -> login timestamp
    """
    error_counts: dict[str, int] = defaultdict(int)
    api_latencies: dict[str, list[int]] = defaultdict(list)
    active_sessions: dict[str, str] = {}

    for entry in entries:
        log_type = entry.get("type")

        if log_type == "ERR":
            error_counts[entry["message"]] += 1

        elif log_type == "WARN":
            # WARN messages are parsed but not included in the report/error counts,
            # matching the original pipeline behaviour.
            pass

        elif log_type == "USR":
            uid = entry["uid"]
            action = entry["action"]
            if "logged in" in action:
                active_sessions[uid] = entry["timestamp"]
            elif "logged out" in action and uid in active_sessions:
                active_sessions.pop(uid)

        elif log_type == "API":
            api_latencies[entry["endpoint"]].append(int(entry["duration_ms"]))

    return {
        "error_counts": dict(error_counts),
        "api_latencies": dict(api_latencies),
        "active_sessions": active_sessions,
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(data: dict, db_path: str) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Creates the ``errors`` and ``api_metrics`` tables if they do not exist.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
        """
    )

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    for msg, count in data["error_counts"].items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in data["api_latencies"].items():
        avg_ms = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_report(data: dict, output_path: str) -> None:
    """Render an HTML report summarising errors, API latency, and active sessions."""
    error_counts = data["error_counts"]
    api_latencies = data["api_latencies"]
    active_sessions = data["active_sessions"]

    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in error_counts.items():
        escaped_msg = err_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"<li><b>{escaped_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    """End-to-end pipeline: extract, transform, load, and report."""
    config = get_config()
    log_file = str(config["log_file"])
    db_path = str(config["db_path"])

    print(f"Connecting to {config['db_host']}:{config['db_port']} as {config['db_user']}...")

    entries = extract_logs(log_file)
    data = transform_log_entries(entries)
    load_to_database(data, db_path)
    generate_report(data, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


def _seed_demo_log(log_file: str) -> None:
    """Create a demo log file if none exists."""
    path = Path(log_file)
    if path.exists():
        return
    path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    _seed_demo_log(LOG_FILE)
    run_pipeline()
