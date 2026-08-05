"""Refactored log-processing pipeline.

Reads server logs, aggregates errors and API latency metrics, persists them to
SQLite, and writes an HTML report.  All configuration is externalised via
environment variables.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> Dict[str, str]:
    """Load runtime configuration from environment variables.

    Returns:
        A dictionary with keys: DB_PATH, LOG_FILE, DB_HOST, DB_PORT, DB_USER,
        DB_PASS.
    """
    return {
        "DB_PATH": os.environ.get("DB_PATH", "metrics.db"),
        "LOG_FILE": os.environ.get("LOG_FILE", "server.log"),
        "DB_HOST": os.environ.get("DB_HOST", "localhost"),
        "DB_PORT": os.environ.get("DB_PORT", "5432"),
        "DB_USER": os.environ.get("DB_USER", "admin"),
        "DB_PASS": os.environ.get("DB_PASS", ""),
    }


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_log_data(log_path: str) -> Tuple[List[Dict], List[Dict], Dict[str, str]]:
    """Parse the server log file into structured records.

    Args:
        log_path: Path to the log file on disk.

    Returns:
        A 3-tuple of (errors, api_calls, sessions):
        - errors: list of error dicts with keys ``dt`` and ``msg``.
        - api_calls: list of API call dicts with keys ``dt``, ``endpoint``, ``ms``.
        - sessions: mapping of user_id -> login_dt for currently active sessions.
    """
    errors: List[Dict] = []
    api_calls: List[Dict] = []
    sessions: Dict[str, str] = {}

    line_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (\w+) (.*)$"
    )
    user_pattern = re.compile(r"User (\d+) (.+)")
    api_pattern = re.compile(r"API (\S+) took (\d+)ms")

    if not os.path.exists(log_path):
        return errors, api_calls, sessions

    with open(log_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            match = line_pattern.match(line)
            if not match:
                continue

            dt = f"{match.group(1)} {match.group(2)}"
            level = match.group(3)
            remainder = match.group(4)

            if level == "ERROR":
                errors.append({"dt": dt, "msg": remainder})
            elif level == "WARN":
                # Warnings are recorded but not surfaced in the report.
                continue
            elif level == "INFO":
                user_match = user_pattern.match(remainder)
                api_match = api_pattern.match(remainder)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action and uid in sessions:
                        sessions.pop(uid)
                elif api_match:
                    api_calls.append({
                        "dt": dt,
                        "endpoint": api_match.group(1),
                        "ms": int(api_match.group(2)),
                    })

    return errors, api_calls, sessions


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_metrics(
    errors: List[Dict], api_calls: List[Dict]
) -> Tuple[Dict[str, int], Dict[str, List[int]]]:
    """Aggregate extracted records into summary metrics.

    Args:
        errors: List of error dicts.
        api_calls: List of API call dicts.

    Returns:
        A 2-tuple of (error_counts, endpoint_stats):
        - error_counts: mapping of error message -> occurrence count.
        - endpoint_stats: mapping of endpoint -> list of response times in ms.
    """
    error_counts: Dict[str, int] = {}
    for err in errors:
        msg = err["msg"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_stats: Dict[str, List[int]] = {}
    for call in api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    return error_counts, endpoint_stats


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Mapping of error message -> count.
        endpoint_stats: Mapping of endpoint -> list of response times.
    """
    now = datetime.datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, times in endpoint_stats.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(
    error_counts: Dict[str, int],
    endpoint_stats: Dict[str, List[int]],
    active_sessions: int,
    output_path: str,
) -> None:
    """Write the HTML report to disk.

    Args:
        error_counts: Mapping of error message -> count.
        endpoint_stats: Mapping of endpoint -> list of response times.
        active_sessions: Number of currently active user sessions.
        output_path: Destination path for the HTML file.
    """
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

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = load_config()

    print(
        f"Connecting to {config['DB_HOST']}:{config['DB_PORT']} "
        f"as {config['DB_USER']}..."
    )

    errors, api_calls, sessions = extract_log_data(config["LOG_FILE"])
    error_counts, endpoint_stats = transform_metrics(errors, api_calls)
    load_to_database(config["DB_PATH"], error_counts, endpoint_stats)
    generate_report(
        error_counts,
        endpoint_stats,
        len(sessions),
        "report.html",
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
