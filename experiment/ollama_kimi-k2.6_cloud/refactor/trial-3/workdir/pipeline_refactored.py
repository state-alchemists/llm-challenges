"""Server log pipeline: parses server logs and generates a metrics report.

Follows an Extract → Transform → Load pattern:
- Extract: parse log lines into structured events
- Transform: aggregate error counts, API latencies, and active sessions
- Load: persist metrics to SQLite and emit an HTML report
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, NamedTuple


# ---------------------------------------------------------------------------
# Configuration (read from environment)
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ParsedLog(NamedTuple):
    """Container for all extracted log events."""
    errors: List["ErrorEvent"]
    api_calls: List["ApiCallEvent"]
    user_events: List["UserEvent"]


class ErrorEvent(NamedTuple):
    """A single ERROR-level log event."""
    dt: str
    message: str


class ApiCallEvent(NamedTuple):
    """A single API latency log event."""
    dt: str
    endpoint: str
    ms: int


class UserEvent(NamedTuple):
    """A single user session log event."""
    dt: str
    uid: str
    action: str


class TransformedMetrics(NamedTuple):
    """Aggregated metrics ready for Load."""
    error_counts: Dict[str, int]
    endpoint_avg_ms: Dict[str, float]
    active_sessions: int


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

LOG_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) "
    r"(?P<level>\w+) "
    r"(?P<message>.*)$"
)

USER_RE = re.compile(r"User (?P<uid>\S+) (?P<action>.+)")
API_RE = re.compile(r"API (?P<endpoint>\S+) took (?P<ms>\d+)ms")


def extract_log_events(log_path: str) -> ParsedLog:
    """Parse *log_path* and return structured events."""
    errors: List[ErrorEvent] = []
    api_calls: List[ApiCallEvent] = []
    user_events: List[UserEvent] = []

    if not os.path.exists(log_path):
        return ParsedLog(errors=errors, api_calls=api_calls, user_events=user_events)

    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            level = match.group("level")
            dt = f"{match.group('date')} {match.group('time')}"
            message = match.group("message")

            if level == "ERROR":
                errors.append(ErrorEvent(dt=dt, message=message))
            elif level == "INFO":
                user_match = USER_RE.search(message)
                if user_match:
                    user_events.append(
                        UserEvent(
                            dt=dt,
                            uid=user_match.group("uid"),
                            action=user_match.group("action"),
                        )
                    )
                else:
                    api_match = API_RE.search(message)
                    if api_match:
                        api_calls.append(
                            ApiCallEvent(
                                dt=dt,
                                endpoint=api_match.group("endpoint"),
                                ms=int(api_match.group("ms")),
                            )
                        )
            # WARN entries are intentionally ignored — they were not surfaced
            # in the legacy report output.

    return ParsedLog(errors=errors, api_calls=api_calls, user_events=user_events)


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform_metrics(parsed: ParsedLog) -> TransformedMetrics:
    """Aggregate extracted events into summary metrics."""
    error_counts: Dict[str, int] = {}
    for err in parsed.errors:
        error_counts[err.message] = error_counts.get(err.message, 0) + 1

    endpoint_times: Dict[str, List[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.ms)

    endpoint_avg_ms: Dict[str, float] = {}
    for ep, times in endpoint_times.items():
        endpoint_avg_ms[ep] = sum(times) / len(times)

    sessions: Dict[str, str] = {}
    for evt in parsed.user_events:
        if "logged in" in evt.action:
            sessions[evt.uid] = evt.dt
        elif "logged out" in evt.action and evt.uid in sessions:
            sessions.pop(evt.uid)

    return TransformedMetrics(
        error_counts=error_counts,
        endpoint_avg_ms=endpoint_avg_ms,
        active_sessions=len(sessions),
    )


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_to_database(metrics: TransformedMetrics, db_path: str) -> None:
    """Persist *metrics* to SQLite at *db_path* using parameterized queries."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = datetime.datetime.now()

    for msg, count in metrics.error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for ep, avg in metrics.endpoint_avg_ms.items():
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, ep, avg),
        )

    conn.commit()
    conn.close()


def generate_report(metrics: TransformedMetrics, report_path: str) -> None:
    """Write an HTML report to *report_path*."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.endpoint_avg_ms.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{metrics.active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(out)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    parsed = extract_log_events(LOG_FILE)
    metrics = transform_metrics(parsed)
    load_to_database(metrics, DB_PATH)
    generate_report(metrics, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
