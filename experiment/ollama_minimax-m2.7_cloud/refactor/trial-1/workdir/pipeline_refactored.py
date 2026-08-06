"""
Pipeline: Parse server logs → Store metrics → Generate HTML report.

Architecture follows the ETL pattern:
  Extract  — read and parse log lines with regex
  Transform — aggregate errors, track sessions, compute API latency
  Load     — write to SQLite and produce report.html

Configuration is read from environment variables:
  DB_PATH, LOG_FILE, DB_HOST, DB_PORT, DB_USER, DB_PASS
"""

import datetime
import os
import re
import sqlite3
from typing import Dict, List, NamedTuple, Optional

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH: str = os.environ.get("DB_PATH", "metrics.db")
LOG_FILE: str = os.environ.get("LOG_FILE", "server.log")
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: int = int(os.environ.get("DB_PORT", "5432"))
DB_USER: str = os.environ.get("DB_USER", "admin")
DB_PASS: str = os.environ.get("DB_PASS", "password123")

# ── Types ──────────────────────────────────────────────────────────────────────

# Log entry kinds
Kind = str  # "ERR" | "USR" | "API" | "WARN"


class LogEntry(NamedTuple):
    """Structured log record produced by the Extract phase."""

    dt: datetime.datetime
    kind: Kind
    # Always present for their respective kinds; None for other kinds.
    message: Optional[str] = None      # ERR, WARN
    user_id: Optional[str] = None      # USR
    action: Optional[str] = None       # USR
    endpoint: Optional[str] = None     # API
    latency_ms: Optional[int] = None   # API


class AggregatedError(NamedTuple):
    """Error message with its total occurrence count."""

    message: str
    occurrences: int


class ApiMetric(NamedTuple):
    """API endpoint with its mean latency in ms."""

    endpoint: str
    avg_ms: float


# ── Extract ───────────────────────────────────────────────────────────────────

# Regex patterns — each captures the relevant fields from a log line.
# Format: "YYYY-MM-DD HH:MM:SS LEVEL extra..."
_RE_ERROR = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (?P<msg>.+)$"
)
_RE_USER = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"User (?P<uid>\S+) (?P<action>logged in|logged out)$"
)
_RE_API = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO "
    r"API (?P<ep>\S+) took (?P<ms>\d+)ms$"
)
_RE_WARN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) WARN (?P<msg>.+)$"
)


def extract_log_entries(path: str) -> List[LogEntry]:
    """
    Read *path* and parse every line into a ``LogEntry``.

    Supports four log-line formats:
      ERROR <message>
      INFO User <id> logged in|logged out
      INFO API <endpoint> took <N>ms
      WARN <message>
    """
    entries: List[LogEntry] = []

    if not os.path.exists(path):
        return entries

    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            m = _RE_ERROR.match(line)
            if m:
                entries.append(
                    LogEntry(
                        dt=datetime.datetime.fromisoformat(m.group("ts").replace(" ", "T")),
                        kind="ERR",
                        message=m.group("msg"),
                    )
                )
                continue

            m = _RE_USER.match(line)
            if m:
                entries.append(
                    LogEntry(
                        dt=datetime.datetime.fromisoformat(m.group("ts").replace(" ", "T")),
                        kind="USR",
                        user_id=m.group("uid"),
                        action=m.group("action"),
                    )
                )
                continue

            m = _RE_API.match(line)
            if m:
                entries.append(
                    LogEntry(
                        dt=datetime.datetime.fromisoformat(m.group("ts").replace(" ", "T")),
                        kind="API",
                        endpoint=m.group("ep"),
                        latency_ms=int(m.group("ms")),
                    )
                )
                continue

            m = _RE_WARN.match(line)
            if m:
                entries.append(
                    LogEntry(
                        dt=datetime.datetime.fromisoformat(m.group("ts").replace(" ", "T")),
                        kind="WARN",
                        message=m.group("msg"),
                    )
                )

    return entries


# ── Transform ─────────────────────────────────────────────────────────────────

def transform_entries(
    entries: List[LogEntry],
) -> tuple[Dict[str, int], List[LogEntry], Dict[str, str]]:
    """
    Aggregate *entries* into three outputs:

    *error_counts* — mapping error message → number of occurrences
    *api_calls*    — all log entries whose kind is "API"
    *sessions*     — mapping user_id → login timestamp; logout removes the key

    WARN entries are parsed but not included in the HTML report (matching the
    original behaviour).
    """
    error_counts: Dict[str, int] = {}
    api_calls: List[LogEntry] = []
    sessions: Dict[str, str] = {}  # user_id → login timestamp string

    for e in entries:
        if e.kind == "ERR":
            msg: str = e.message  # type: ignore[assignment] — guaranteed non-None for ERR kind
            assert msg is not None
            error_counts[msg] = error_counts.get(msg, 0) + 1

        elif e.kind == "USR":
            uid: str = e.user_id  # type: ignore[assignment] — regex guarantees non-None for USR kind
            assert uid is not None
            if e.action == "logged in":
                sessions[uid] = str(e.dt)
            elif e.action == "logged out" and uid in sessions:
                sessions.pop(uid)

        elif e.kind == "API":
            api_calls.append(e)

        # WARN entries are intentionally ignored in the report.

    return error_counts, api_calls, sessions


# ── Load ──────────────────────────────────────────────────────────────────────

def load_to_db(
    errors: Dict[str, int],
    api_calls: List[LogEntry],
    db_path: str = DB_PATH,
    timestamp: Optional[datetime.datetime] = None,
) -> None:
    """
    Persist *errors* and *api_calls* to the SQLite database at *db_path*.

    Uses parameterised queries (``?`` placeholders) to prevent SQL injection.
    Creates both tables if they do not exist.
    """
    ts = timestamp or datetime.datetime.now()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    for msg, count in errors.items():
        cur.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (str(ts), msg, count),
        )

    # Aggregate API calls by endpoint before inserting
    by_endpoint: Dict[str, List[int]] = {}
    for call in api_calls:
        ep: str = call.endpoint  # type: ignore[assignment] — guaranteed non-None for API kind
        ms: int = call.latency_ms  # type: ignore[assignment]
        assert ep is not None and ms is not None
        by_endpoint.setdefault(ep, []).append(ms)

    for ep, latencies in by_endpoint.items():
        avg = sum(latencies) / len(latencies)
        cur.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (str(ts), ep, avg),
        )

    conn.commit()
    conn.close()


def generate_html_report(
    error_counts: Dict[str, int],
    api_calls: List[LogEntry],
    sessions: Dict[str, str],
    output_path: str = "report.html",
) -> str:
    """
    Build an HTML report and write it to *output_path*.

    Returns the HTML string (matching the original ``proc_data`` return value).
    Report sections: Error Summary, API Latency table, Active Sessions count.
    """
    by_endpoint: Dict[str, List[int]] = {}
    for call in api_calls:
        ep: str = call.endpoint  # type: ignore[assignment] — guaranteed non-None for API kind
        ms: int = call.latency_ms  # type: ignore[assignment]
        assert ep is not None and ms is not None
        by_endpoint.setdefault(ep, []).append(ms)

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for msg, count in error_counts.items():
        out += f"<li><b>{msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, latencies in by_endpoint.items():
        avg = sum(latencies) / len(latencies)
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(output_path, "w") as fh:
        fh.write(out)

    return out


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    """Run the full ETL pipeline: extract → transform → load → report."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    entries = extract_log_entries(LOG_FILE)
    print(f"Extracted {len(entries)} entries from {LOG_FILE}")

    error_counts, api_calls, sessions = transform_entries(entries)
    print(f"Found {len(error_counts)} unique errors, {len(api_calls)} API calls")

    load_to_db(error_counts, api_calls)
    generate_html_report(error_counts, api_calls, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    # Bootstrap a minimal sample log so the script can run out-of-the-box.
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as fh:
            fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    run()
