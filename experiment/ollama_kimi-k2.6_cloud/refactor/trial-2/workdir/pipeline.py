"""ETL pipeline that processes server logs and generates a metrics report.

Extracts events from a plain-text log file, transforms them into aggregated
statistics, loads the results into a SQLite database, and writes report.html.
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Regex patterns for log-line parsing
# ---------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (.*)$")
_USER_ACTION_RE = re.compile(r"User (\S+) (.+)")
_API_ENDPOINT_RE = re.compile(r"API (\S+)")
_API_DURATION_RE = re.compile(r"took (\d+)ms")


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


def get_config() -> Config:
    """Load configuration from environment variables.

    Falls back to the original hard-coded defaults so that the script remains
    runnable out-of-the-box while allowing production overrides via env vars.
    """
    return Config(
        db_path=os.environ.get("DB_PATH", "metrics.db"),
        log_file=os.environ.get("LOG_FILE", "server.log"),
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_user=os.environ.get("DB_USER", "admin"),
        db_pass=os.environ.get("DB_PASS", "password123"),
    )


def _ensure_sample_log(log_file_path: str) -> None:
    """Create a sample log file if none exists."""
    path = Path(log_file_path)
    if path.exists():
        return
    path.write_text(
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )


def extract(log_file_path: str) -> list[dict]:
    """Read and parse server log lines into structured records.

    Args:
        log_file_path: Path to the server log file.

    Returns:
        A list of dictionaries, each representing a parsed log event.
        Possible record types are ``error``, ``warn``, ``user``, and ``api``.
    """
    records: list[dict] = []
    path = Path(log_file_path)

    if not path.exists():
        return records

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        match = _LOG_LINE_RE.match(line)
        if not match:
            continue

        dt_str, level, message = match.groups()

        if level == "ERROR":
            records.append({"type": "error", "dt": dt_str, "message": message})
        elif level == "WARN":
            records.append({"type": "warn", "dt": dt_str, "message": message})
        elif level == "INFO":
            if "User" in message:
                user_match = _USER_ACTION_RE.match(message)
                if user_match:
                    user_id, action = user_match.groups()
                    records.append(
                        {
                            "type": "user",
                            "dt": dt_str,
                            "user_id": user_id,
                            "action": action,
                        }
                    )
            elif "API" in message:
                endpoint_match = _API_ENDPOINT_RE.search(message)
                if endpoint_match:
                    endpoint = endpoint_match.group(1)
                    duration_match = _API_DURATION_RE.search(message)
                    duration = int(duration_match.group(1)) if duration_match else 0
                    records.append(
                        {
                            "type": "api",
                            "dt": dt_str,
                            "endpoint": endpoint,
                            "ms": duration,
                        }
                    )

    return records


def transform(records: list[dict]) -> dict:
    """Aggregate parsed log records into summary statistics.

    Args:
        records: List of parsed log records from the :func:`extract` step.

    Returns:
        Dictionary with the following keys:
        - ``error_counts``: ``dict[str, int]`` mapping error message to occurrence count.
        - ``api_latencies``: ``dict[str, list[int]]`` mapping endpoint to latency samples.
        - ``active_sessions``: ``dict[str, str]`` mapping active user ID to login timestamp.
    """
    error_counts: dict[str, int] = defaultdict(int)
    api_latencies: dict[str, list[int]] = defaultdict(list)
    active_sessions: dict[str, str] = {}

    for record in records:
        if record["type"] == "error":
            error_counts[record["message"]] += 1
        elif record["type"] == "api":
            api_latencies[record["endpoint"]].append(record["ms"])
        elif record["type"] == "user":
            user_id = record["user_id"]
            action = record["action"]
            if "logged in" in action:
                active_sessions[user_id] = record["dt"]
            elif "logged out" in action and user_id in active_sessions:
                active_sessions.pop(user_id)

    return {
        "error_counts": dict(error_counts),
        "api_latencies": dict(api_latencies),
        "active_sessions": active_sessions,
    }


def load(db_path: str, data: dict) -> None:
    """Persist aggregated data to SQLite and generate ``report.html``.

    Args:
        db_path: Path to the SQLite database file.
        data: Transformed data containing ``error_counts``, ``api_latencies``,
            and ``active_sessions``.
    """
    error_counts: dict[str, int] = data["error_counts"]
    api_latencies: dict[str, list[int]] = data["api_latencies"]
    active_sessions: dict[str, str] = data["active_sessions"]

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

    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

    # ------------------------------------------------------------------
    # Generate HTML report
    # ------------------------------------------------------------------
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in api_latencies.items():
        avg = sum(times) / len(times)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>\n"

    Path("report.html").write_text(out)


def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    config = get_config()
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    _ensure_sample_log(config.log_file)
    records = extract(config.log_file)
    data = transform(records)
    load(config.db_path, data)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
