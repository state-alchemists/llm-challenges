"""Server log pipeline: extract events from logs, transform metrics, and load to DB + HTML report."""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config() -> Dict[str, str]:
    """Load pipeline configuration from environment variables.

    Returns:
        Mapping with keys: db_path, log_file, db_host, db_port, db_user, db_pass.
    """
    return {
        "db_path": os.getenv("METRICS_DB_PATH", "metrics.db"),
        "log_file": os.getenv("SERVER_LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_pass": os.getenv("DB_PASS", "password123"),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

_LOG_PATTERNS = {
    "error": re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.*)$"),
    "warn": re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.*)$"),
    "user": re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.*)$"),
    "api": re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"),
}


def extract(log_file: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, str]]:
    """Parse the server log and return raw events.

    Args:
        log_file: Path to the server log file.

    Returns:
        A tuple of (error_entries, api_calls, sessions).
        * error_entries – list of dicts with keys ``timestamp`` and ``message``.
        * api_calls – list of dicts with keys ``timestamp``, ``endpoint``, ``duration_ms``.
        * sessions – mapping of user_id -> login timestamp for currently active sessions.
    """
    error_entries: List[Dict[str, str]] = []
    api_calls: List[Dict[str, str]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file):
        return error_entries, api_calls, sessions

    with open(log_file, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue

            match = _LOG_PATTERNS["error"].match(line)
            if match:
                error_entries.append({"timestamp": match.group(1), "message": match.group(2)})
                continue

            match = _LOG_PATTERNS["warn"].match(line)
            if match:
                # WARN entries are parsed for behavioural parity with the original
                # script but are not surfaced in the report.
                continue

            match = _LOG_PATTERNS["user"].match(line)
            if match:
                timestamp, uid, action = match.group(1), match.group(2), match.group(3)
                if "logged in" in action:
                    sessions[uid] = timestamp
                elif "logged out" in action and uid in sessions:
                    sessions.pop(uid)
                continue

            match = _LOG_PATTERNS["api"].match(line)
            if match:
                api_calls.append(
                    {
                        "timestamp": match.group(1),
                        "endpoint": match.group(2),
                        "duration_ms": match.group(3),
                    }
                )
                continue

    return error_entries, api_calls, sessions


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(
    error_entries: List[Dict[str, str]],
    api_calls: List[Dict[str, str]],
    sessions: Dict[str, str],
) -> Tuple[Dict[str, int], Dict[str, List[int]], int]:
    """Aggregate raw events into report-ready metrics.

    Args:
        error_entries: Raw error events from the extract phase.
        api_calls: Raw API call events from the extract phase.
        sessions: Active session mapping from the extract phase.

    Returns:
        A tuple of (error_counts, endpoint_stats, active_session_count).
        * error_counts – mapping of error message -> occurrence count.
        * endpoint_stats – mapping of endpoint -> list of durations in milliseconds.
        * active_session_count – number of currently active sessions.
    """
    error_counts: Dict[str, int] = {}
    for entry in error_entries:
        msg = entry["message"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        endpoint_stats[call["endpoint"]].append(int(call["duration_ms"]))

    return error_counts, dict(endpoint_stats), len(sessions)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load(
    db_path: str,
    db_host: str,
    db_port: str,
    db_user: str,
    db_pass: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions: int,
) -> None:
    """Persist metrics to SQLite and generate ``report.html``.

    Args:
        db_path: Path to the SQLite database file.
        db_host: Database host (logged for display only).
        db_port: Database port (logged for display only).
        db_user: Database username (logged for display only).
        db_pass: Database password (logged for display only).
        error_counts: Aggregated error message counts.
        endpoint_stats: Aggregated API endpoint durations.
        active_sessions: Number of currently active sessions.
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")

    now = str(datetime.datetime.now())

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()

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
    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open("report.html", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    config = get_config()
    error_entries, api_calls, sessions = extract(config["log_file"])
    error_counts, endpoint_stats, active_sessions = transform(error_entries, api_calls, sessions)
    load(
        db_path=config["db_path"],
        db_host=config["db_host"],
        db_port=config["db_port"],
        db_user=config["db_user"],
        db_pass=config["db_pass"],
        error_counts=error_counts,
        endpoint_stats=endpoint_stats,
        active_sessions=active_sessions,
    )


if __name__ == "__main__":
    cfg = get_config()
    log_file = cfg["log_file"]
    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
