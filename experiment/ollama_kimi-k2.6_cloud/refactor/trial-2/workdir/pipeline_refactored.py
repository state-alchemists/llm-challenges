"""Server log processing pipeline.

Reads server logs, aggregates metrics, persists them to a SQLite database,
and generates an HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> dict[str, str]:
    """Load runtime configuration from environment variables.

    Falls back to the legacy defaults so existing deployments continue to work
    until the variables are exported.

    Returns:
        A mapping with keys: ``db_path``, ``log_file``, ``db_host``,
        ``db_port``, ``db_user``, ``db_pass``.
    """
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": os.environ.get("DB_PORT", "5432"),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_lines(log_path: str) -> list[str]:
    """Read non-empty lines from the log file.

    Args:
        log_path: Absolute or relative path to the server log.

    Returns:
        Stripped, non-empty log lines.
    """
    if not os.path.exists(log_path):
        return []

    with open(log_path, "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

_LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"(?P<level>INFO|ERROR|WARN) "
    r"(?P<message>.+?)\s*$"
)

_USER_RE = re.compile(r"^User (?P<user_id>\S+) (?P<action>.+)$")
_API_RE = re.compile(r"^API (?P<endpoint>\S+) took (?P<duration>\d+)ms$")


def transform_lines(
    lines: list[str],
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, str]]:
    """Parse raw log lines into structured aggregates.

    Args:
        lines: Output of :func:`extract_lines`.

    Returns:
        A 3-tuple of:
        1. **error_counts** – mapping of error message → occurrence count.
        2. **api_buckets** – mapping of endpoint → list of observed latencies (ms).
        3. **active_sessions** – mapping of user ID → login timestamp for users
           that are currently logged in.
    """
    error_counts: dict[str, int] = {}
    api_buckets: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}

    for line in lines:
        match = _LOG_RE.match(line)
        if not match:
            continue

        level = match.group("level")
        message = match.group("message")
        timestamp = match.group("timestamp")

        if level == "ERROR":
            error_counts[message] = error_counts.get(message, 0) + 1

        elif level == "INFO":
            user_match = _USER_RE.match(message)
            if user_match:
                user_id = user_match.group("user_id")
                action = user_match.group("action")
                if "logged in" in action:
                    sessions[user_id] = timestamp
                elif "logged out" in action and user_id in sessions:
                    sessions.pop(user_id)
                continue

            api_match = _API_RE.match(message)
            if api_match:
                endpoint = api_match.group("endpoint")
                duration = int(api_match.group("duration"))
                api_buckets.setdefault(endpoint, []).append(duration)

        # WARN messages are intentionally ignored – the original pipeline
        # collected them but never surfaced them in the report or DB.

    return error_counts, api_buckets, sessions


def compute_api_averages(api_buckets: dict[str, list[int]]) -> dict[str, float]:
    """Calculate mean latency for each endpoint.

    Args:
        api_buckets: Mapping produced by :func:`transform_lines`.

    Returns:
        Endpoint → average latency in milliseconds.
    """
    return {
        endpoint: sum(times) / len(times)
        for endpoint, times in api_buckets.items()
        if times
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
) -> None:
    """Persist aggregated metrics to SQLite using *parameterized* queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Error message → occurrence count.
        api_averages: Endpoint → average latency (ms).
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now_str = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now_str, msg, count),
        )

    for endpoint, avg in api_averages.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now_str, endpoint, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report_html(
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    active_sessions: dict[str, str],
) -> str:
    """Build the HTML report string preserving the original layout.

    Args:
        error_counts: Error message → occurrence count.
        api_averages: Endpoint → average latency (ms).
        active_sessions: Currently active user sessions (user ID → login time).

    Returns:
        Complete HTML document.
    """
    lines: list[str] = [
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

    for ep, avg in api_averages.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    return "\n".join(lines)


def write_report(html: str, report_path: str = "report.html") -> None:
    """Write the HTML report to disk.

    Args:
        html: The HTML content.
        report_path: Destination file path.
    """
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the full ETL pipeline."""
    config = load_config()

    print(
        f"Connecting to {config['db_host']}:{config['db_port']} "
        f"as {config['db_user']}..."
    )

    raw_lines = extract_lines(config["log_file"])
    error_counts, api_buckets, sessions = transform_lines(raw_lines)
    api_averages = compute_api_averages(api_buckets)

    load_to_database(config["db_path"], error_counts, api_averages)

    report = generate_report_html(error_counts, api_averages, sessions)
    write_report(report, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    log_file = os.environ.get("LOG_FILE", "server.log")
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    main()
