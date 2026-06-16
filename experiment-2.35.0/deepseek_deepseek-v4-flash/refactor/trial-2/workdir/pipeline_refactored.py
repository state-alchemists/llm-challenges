"""Process server logs and generate a system report (HTML).

Reads structured log files, parses ERROR / INFO User / INFO API / WARN lines,
persists aggregated metrics to SQLite, and writes a report.html with an error
summary, API latency table, and active session count.

Configuration is read from environment variables (see Config class).
"""

import datetime
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple


# ── Regex patterns for log line parsing ──────────────────────────────
# Format: <YYYY-MM-DD HH:MM:SS> <LEVEL> <message>
_TIMESTAMP_RE = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"

ERROR_RE = re.compile(
    rf"^{_TIMESTAMP_RE} ERROR (?P<message>.+)$"
)
USER_RE = re.compile(
    rf"^(?P<timestamp>{_TIMESTAMP_RE}) INFO User (?P<user_id>\d+) (?P<action>.+)$"
)
API_RE = re.compile(
    rf"^{_TIMESTAMP_RE} INFO API (?P<endpoint>\S+) took (?P<duration>\d+)ms$"
)
WARN_RE = re.compile(
    rf"^{_TIMESTAMP_RE} WARN (?P<message>.+)$"
)


# ── Configuration ────────────────────────────────────────────────────


class Config:
    """Read-only configuration sourced from environment variables.

    Environment variables (with defaults):
        LOG_FILE    – path to the server log to process ("server.log")
        DB_PATH     – path to the SQLite database ("metrics.db")
        DB_HOST     – database host (reserved, not used by SQLite)
        DB_PORT     – database port (reserved, not used by SQLite)
        DB_USER     – database user (reserved, not used by SQLite)
        DB_PASS     – database password (reserved, not used by SQLite)
        REPORT_FILE – path for the generated HTML report ("report.html")
    """

    def __init__(self) -> None:
        self.log_file: str = os.environ.get("LOG_FILE", "server.log")
        self.db_path: str = os.environ.get("DB_PATH", "metrics.db")
        self.db_host: str = os.environ.get("DB_HOST", "localhost")
        self.db_port: int = int(os.environ.get("DB_PORT", "5432"))
        self.db_user: str = os.environ.get("DB_USER", "admin")
        self.db_pass: str = os.environ.get("DB_PASS", "")
        self.report_file: str = os.environ.get("REPORT_FILE", "report.html")


# ── Extract ──────────────────────────────────────────────────────────


ParsedEvent = Dict[str, str | int]
ActiveSessions = Dict[str, str]
ApiCall = Dict[str, str | int]


def parse_log_file(path: str) -> Tuple[List[ParsedEvent], ActiveSessions, List[ApiCall]]:
    """Read and parse *path* line-by-line, returning structured records.

    Returns a tuple of:
        - events:   all parsed log entries except raw API-call rows
                    (ERROR, User action, WARN)
        - sessions: current active session map {user_id: timestamp}
        - api_calls: raw API-call records for latency aggregation
    """
    events: List[ParsedEvent] = []
    sessions: ActiveSessions = {}
    api_calls: List[ApiCall] = []

    if not os.path.exists(path):
        return events, sessions, api_calls

    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n")

            m = ERROR_RE.match(line)
            if m:
                events.append({
                    "type": "ERR",
                    "message": m.group("message"),
                })
                continue

            m = USER_RE.match(line)
            if m:
                uid = m.group("user_id")
                ts = m.group("timestamp")
                action = m.group("action")
                if "logged in" in action:
                    sessions[uid] = ts
                elif "logged out" in action and uid in sessions:
                    del sessions[uid]
                events.append({
                    "type": "USR",
                    "user_id": uid,
                    "action": action,
                })
                continue

            m = API_RE.match(line)
            if m:
                api_calls.append({
                    "endpoint": m.group("endpoint"),
                    "duration_ms": int(m.group("duration")),
                })
                continue

            m = WARN_RE.match(line)
            if m:
                events.append({
                    "type": "WARN",
                    "message": m.group("message"),
                })
                # continue — explicit for clarity; next iteration anyway

    return events, sessions, api_calls


# ── Transform ────────────────────────────────────────────────────────


def aggregate_errors(events: List[ParsedEvent]) -> Dict[str, int]:
    """Count occurrences of each unique error message."""
    counts: Dict[str, int] = {}
    for ev in events:
        if ev.get("type") == "ERR":
            msg = str(ev.get("message", ""))
            counts[msg] = counts.get(msg, 0) + 1
    return counts


def compute_api_latency(api_calls: List[ApiCall]) -> Dict[str, float]:
    """Compute average latency (ms) per API endpoint."""
    buckets: Dict[str, List[int]] = defaultdict(list)
    for call in api_calls:
        buckets[str(call["endpoint"])].append(int(call["duration_ms"]))
    return {
        ep: sum(times) / len(times)
        for ep, times in buckets.items()
    }


# ── Load ─────────────────────────────────────────────────────────────


def init_database(db_path: str) -> sqlite3.Connection:
    """Open *db_path* and create tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors "
        "(dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics "
        "(dt TEXT, endpoint TEXT, avg_ms REAL)"
    )
    conn.commit()
    return conn


def persist_errors(conn: sqlite3.Connection, error_counts: Dict[str, int]) -> None:
    """Insert aggregated error counts using parameterised queries."""
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for msg, count in error_counts.items():
        cur.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )
    conn.commit()


def persist_api_metrics(
    conn: sqlite3.Connection, api_latency: Dict[str, float]
) -> None:
    """Insert per-endpoint average latency using parameterised queries."""
    now = datetime.datetime.now().isoformat()
    cur = conn.cursor()
    for endpoint, avg_ms in api_latency.items():
        cur.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, round(avg_ms, 2)),
        )
    conn.commit()


def generate_report(
    error_counts: Dict[str, int],
    api_latency: Dict[str, float],
    active_session_count: int,
    output_path: str,
) -> None:
    """Write *output_path* as an HTML report with the three required sections."""
    lines: List[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for msg, count in error_counts.items():
        lines.append(f"<li><b>{msg}</b>: {count} occurrences</li>")
    lines.extend(["</ul>", "<h2>API Latency</h2>", "<table border='1'>"])
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep in sorted(api_latency, key=api_latency.__getitem__, reverse=True):
        lines.append(f"<tr><td>{ep}</td><td>{round(api_latency[ep], 1)}</td></tr>")
    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{active_session_count} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])
    with open(output_path, "w") as f:
        f.write("\n".join(lines))


# ── Sample data (preserved from original) ────────────────────────────

_SAMPLE_LOG = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


def _maybe_write_sample_log(path: str) -> None:
    """Write sample log data if *path* does not already exist."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(_SAMPLE_LOG)


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    """Orchestrate the full extract → transform → load pipeline."""
    cfg = Config()

    _maybe_write_sample_log(cfg.log_file)

    # Extract
    events, sessions, api_calls = parse_log_file(cfg.log_file)
    print(f"Parsed {len(events)} events, {len(api_calls)} API calls from {cfg.log_file}")

    # Transform
    error_counts = aggregate_errors(events)
    api_latency = compute_api_latency(api_calls)

    # Load – database
    conn = init_database(cfg.db_path)
    persist_errors(conn, error_counts)
    persist_api_metrics(conn, api_latency)
    conn.close()

    # Load – report
    generate_report(error_counts, api_latency, len(sessions), cfg.report_file)

    print(f"Report written to {cfg.report_file}")
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
