"""
Pipeline: Process server logs and generate an HTML report.

Extracts log data, transforms it into metrics, loads into SQLite
and produces an HTML report.
"""

import datetime
import os
import re
import sqlite3
from pathlib import Path
from typing import TypedDict


# === Configuration via environment variables ===

DB_PATH = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE = os.environ.get("LOG_FILE", "server.log")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "")


# === Type definitions ===

class ErrorEntry(TypedDict):
    dt: str
    msg: str


class ApiCall(TypedDict):
    endpoint: str
    ms: int


class SessionEntry(TypedDict):
    pass


# === Regex patterns ===

_ERROR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$")
_WARN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (.+)$")
_USER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.+)$")
_API_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+) took (\d+)ms$"
)


# === EXTRACT ===

def extract_log_entries(log_path: str) -> tuple[list[ErrorEntry], list[ApiCall], dict]:
    """
    Parse the log file and extract structured records.

    Returns:
        Tuple of (errors, api_calls, active_sessions).
        Errors: list of {dt, msg}.
        API calls: list of {endpoint, ms}.
        Sessions: dict mapping user_id -> login_dt.
    """
    errors: list[ErrorEntry] = []
    api_calls: list[ApiCall] = []
    sessions: dict = {}

    path = Path(log_path)
    if not path.exists():
        return errors, api_calls, sessions

    for line in path.read_text().splitlines():
        if match := _ERROR_RE.match(line):
            errors.append({"dt": match.group(1), "msg": match.group(2)})
        elif match := _WARN_RE.match(line):
            pass  # Warnings are not stored; they appear in the original code only as console output
        elif match := _USER_RE.match(line):
            uid = match.group(2)
            action = match.group(3)
            if "logged in" in action:
                sessions[uid] = match.group(1)
            elif "logged out" in action and uid in sessions:
                del sessions[uid]
        elif match := _API_RE.match(line):
            api_calls.append({
                "endpoint": match.group(2),
                "ms": int(match.group(3)),
            })

    return errors, api_calls, sessions


# === TRANSFORM ===

def transform_error_counts(errors: list[ErrorEntry]) -> dict[str, int]:
    """Aggregate error messages by count."""
    counts: dict[str, int] = {}
    for err in errors:
        counts[err["msg"]] = counts.get(err["msg"], 0) + 1
    return counts


def transform_api_latency(api_calls: list[ApiCall]) -> dict[str, float]:
    """
    Compute average latency per endpoint.

    Returns:
        Dict mapping endpoint -> average latency in ms.
    """
    by_endpoint: dict[str, list[int]] = {}
    for call in api_calls:
        by_endpoint.setdefault(call["endpoint"], []).append(call["ms"])

    return {ep: sum(times) / len(times) for ep, times in by_endpoint.items()}


# === LOAD ===

def load_into_db(
    db_path: str,
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    now: datetime.datetime,
) -> None:
    """
    Write aggregated metrics into SQLite.

    Uses parameterized queries to prevent SQL injection.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            dt TEXT,
            message TEXT,
            count INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_metrics (
            dt TEXT,
            endpoint TEXT,
            avg_ms REAL
        )
    """)

    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now.isoformat(), msg, count),
        )

    for endpoint, avg_ms in api_latency.items():
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now.isoformat(), endpoint, avg_ms),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    error_counts: dict[str, int],
    api_latency: dict[str, float],
    active_session_count: int,
) -> str:
    """Build the HTML report string."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for endpoint, avg in api_latency.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{active_session_count} user(s) currently active</p>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


# === PIPELINE ===

def run_pipeline() -> None:
    """Execute the full ETL pipeline."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    errors, api_calls, sessions = extract_log_entries(LOG_FILE)

    error_counts = transform_error_counts(errors)
    api_latency = transform_api_latency(api_calls)

    now = datetime.datetime.now()
    load_into_db(DB_PATH, error_counts, api_latency, now)

    report = generate_html_report(error_counts, api_latency, len(sessions))
    Path("report.html").write_text(report)

    print(f"Job finished at {now}")


# === ENTRY POINT ===

if __name__ == "__main__":
    if not Path(LOG_FILE).exists():
        Path(LOG_FILE).write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n"
            "2024-01-01 12:05:05 ERROR Database timeout\n"
            "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
            "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
            "2024-01-01 12:10:00 INFO User 42 logged out\n"
        )
    run_pipeline()
