"""Pipeline for processing server logs and generating a metrics report.

Extracts log data, transforms it into metrics, loads into an SQLite database,
and produces an HTML report with error summary, API latency table,
and active session count.

Environment variables:
    DB_PATH: Path to SQLite database (default: metrics.db)
    LOG_FILE: Path to server log file (default: server.log)
    DB_HOST: Database host (default: localhost)
    DB_PORT: Database port (default: 5432)
    DB_USER: Database user (default: admin)
    DB_PASS: Database password (default: empty)
"""

import datetime
import os
import re
import sqlite3


# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "")  # Never hardcode credentials


# ---------------------------------------------------------------------------
# Regex patterns (compiled once, reused)
# ---------------------------------------------------------------------------

# Matches: 2024-01-01 12:00:00 ERROR|Duration INFO|WARN ...
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|INFO|WARN)\s+"
    r"(?P<rest>.+)$"
)

# Matches: User <uid> <action>
_USER_ACTION_RE = re.compile(r"User\s+(?P<uid>\S+)\s+(?P<action>.+)")

# Matches: API <endpoint> took <ms>ms
_API_CALL_RE = re.compile(r"API\s+(?P<endpoint>\S+)\s+took\s+(?P<ms>\d+)ms")


# ---------------------------------------------------------------------------
# EXTRACT stage
# ---------------------------------------------------------------------------


def extract_log_entries(filepath: str) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Parse the log file and return structured records.

    Args:
        filepath: Path to the server log file.

    Returns:
        A 3-tuple of:
        - list of log-entry dicts (errors, user actions, warnings)
        - list of API-call dicts (API latency records)
        - dict mapping user id -> login timestamp (open sessions)
    """
    entries: list[dict] = []
    api_calls: list[dict] = []
    sessions: dict[str, str] = {}

    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found — skipping extraction.")
        return entries, api_calls, sessions

    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _LOG_LINE_RE.match(line)
            if not m:
                continue

            timestamp: str = m.group("timestamp")
            level: str = m.group("level")
            rest: str = m.group("rest")

            if level == "ERROR":
                entries.append({"d": timestamp, "t": "ERR", "m": rest})

            elif level == "INFO" and "User" in rest:
                um = _USER_ACTION_RE.search(rest)
                if not um:
                    continue
                uid: str = um.group("uid")
                action: str = um.group("action").strip()
                if "logged in" in action:
                    sessions[uid] = timestamp
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]
                entries.append({"d": timestamp, "t": "USR", "u": uid, "a": action})

            elif level == "INFO" and "API" in rest:
                am = _API_CALL_RE.search(rest)
                if not am:
                    continue
                api_calls.append({
                    "d": timestamp,
                    "endpoint": am.group("endpoint"),
                    "ms": int(am.group("ms")),
                })

            elif level == "WARN":
                entries.append({"d": timestamp, "t": "WARN", "m": rest})

    return entries, api_calls, sessions


# ---------------------------------------------------------------------------
# TRANSFORM stage
# ---------------------------------------------------------------------------


def transform_error_counts(entries: list[dict]) -> dict[str, int]:
    """Aggregate error and warning messages by text.

    Args:
        entries: Log-entry records from the extract stage.

    Returns:
        Dict mapping message text -> occurrence count.
    """
    counts: dict[str, int] = {}
    for e in entries:
        if e["t"] in ("ERR", "WARN"):
            msg: str = e["m"]
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def transform_api_stats(api_calls: list[dict]) -> dict[str, list[int]]:
    """Group API call durations by endpoint.

    Args:
        api_calls: API-call records from the extract stage.

    Returns:
        Dict mapping endpoint -> list of duration values (ms).
    """
    stats: dict[str, list[int]] = {}
    for call in api_calls:
        stats.setdefault(call["endpoint"], []).append(call["ms"])
    return stats


# ---------------------------------------------------------------------------
# LOAD stage
# ---------------------------------------------------------------------------


def load_to_database(
    db_path: str,
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
) -> None:
    """Write aggregated metrics into SQLite using parameterized queries.

    Args:
        db_path: Path to the SQLite database file.
        error_counts: Message -> count mapping.
        api_stats: Endpoint -> list of duration values.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now: str = datetime.datetime.now().isoformat()

    for msg, count in error_counts.items():
        # Parameterized INSERT — prevents SQL injection
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count)
        )

    for endpoint, durations in api_stats.items():
        avg_ms: float = sum(durations) / len(durations)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg_ms)
        )

    conn.commit()
    conn.close()


def generate_html_report(
    error_counts: dict[str, int],
    api_stats: dict[str, list[int]],
    active_sessions: int,
    output_path: str = "report.html",
) -> None:
    """Write the HTML report to disk.

    Args:
        error_counts: Message -> count mapping.
        api_stats: Endpoint -> list of duration values.
        active_sessions: Number of currently logged-in users.
        output_path: Destination file path.
    """
    now_str: str = datetime.datetime.now().isoformat()

    lines: list[str] = [
        "<html>",
        "<head>",
        f"  <title>System Report — {now_str}</title>",
        "</head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for msg, count in error_counts.items():
        # Escape HTML entities in user-controlled content
        safe_msg: str = (
            msg.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
        )
        lines.append(f"  <li><b>{safe_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, durations in api_stats.items():
        avg_ms: float = sum(durations) / len(durations)
        lines.append(f"  <tr><td>{endpoint}</td><td>{avg_ms:.1f}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_sessions} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_pipeline() -> None:
    """Run the full Extract → Transform → Load pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER} ...")

    entries, api_calls, sessions = extract_log_entries(LOG_FILE)
    error_counts = transform_error_counts(entries)
    api_stats = transform_api_stats(api_calls)

    load_to_database(DB_PATH, error_counts, api_stats)
    generate_html_report(error_counts, api_stats, len(sessions), "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Mirror original behaviour: create a sample log if none exists
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    run_pipeline()
