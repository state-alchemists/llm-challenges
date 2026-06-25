"""Pipeline Log Processor.

Processes server logs, extracts error, user, warning, and api latency metrics,
transforms them, loads them into SQLite safely using parameterized queries,
and generates an HTML summary report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class LogPayload:
    """Dataclass holding the extracted raw data from the server log file."""

    errors: list[dict[str, str]]
    api_calls: list[dict[str, Any]]
    active_sessions: int


# Configurations extracted from environment variables
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_data(log_path: str) -> LogPayload:
    """Extract and parse logs from the log file using regular expressions.

    Tracks errors, API calls, and user sessions.
    """
    errors: list[dict[str, str]] = []
    api_calls: list[dict[str, Any]] = []
    sessions: dict[str, str] = {}

    line_pattern = re.compile(
        r"^(?P<dt>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(?P<lvl>INFO|ERROR|WARN)\s+(?P<msg>.*)$"
    )
    user_pattern = re.compile(r"^User\s+(?P<uid>\S+)\s+(?P<action>.*)$")
    api_pattern = re.compile(r"^API\s+(?P<endpoint>\S+)(?:\s+took\s+(?P<dur>\d+)ms)?")

    if not Path(log_path).exists():
        return LogPayload(errors=errors, api_calls=api_calls, active_sessions=0)

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            match = line_pattern.match(line.strip())
            if not match:
                continue

            dt = match.group("dt")
            lvl = match.group("lvl")
            msg = match.group("msg")

            if lvl == "ERROR":
                errors.append({"dt": dt, "message": msg.strip()})
            elif lvl == "INFO":
                user_match = user_pattern.match(msg)
                if user_match:
                    uid = user_match.group("uid")
                    action = user_match.group("action").strip()
                    if "logged in" in action:
                        sessions[uid] = dt
                    elif "logged out" in action:
                        sessions.pop(uid, None)
                else:
                    api_match = api_pattern.match(msg)
                    if api_match:
                        ep = api_match.group("endpoint")
                        dur_str = api_match.group("dur")
                        dur = int(dur_str) if dur_str is not None else 0
                        api_calls.append({"dt": dt, "endpoint": ep, "ms": dur})

    return LogPayload(
        errors=errors, api_calls=api_calls, active_sessions=len(sessions)
    )


def transform_log_data(payload: LogPayload) -> dict[str, Any]:
    """Transform raw log payloads into structured statistics.

    Calculates error occurrence counts and API endpoint latency averages.
    """
    error_counts: dict[str, int] = {}
    for err in payload.errors:
        msg = err["message"]
        error_counts[msg] = error_counts.get(msg, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in payload.api_calls:
        ep = call["endpoint"]
        endpoint_times.setdefault(ep, []).append(call["ms"])

    api_averages: dict[str, float] = {}
    for ep, times in endpoint_times.items():
        api_averages[ep] = sum(times) / len(times)

    return {
        "error_counts": error_counts,
        "api_averages": api_averages,
        "active_sessions": payload.active_sessions,
    }


def load_data_to_db(
    db_path: str,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
) -> None:
    """Load transformed data into SQLite database using parameterized queries.

    This fixes the SQL injection vulnerabilities present in the original code.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now_str = str(datetime.datetime.now())

        for msg, count in error_counts.items():
            c.execute(
                "INSERT INTO errors VALUES (?, ?, ?)", (now_str, msg, count)
            )

        for ep, avg in api_averages.items():
            c.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)", (now_str, ep, avg)
            )

        conn.commit()
    finally:
        conn.close()


def generate_report(
    report_path: str,
    error_counts: dict[str, int],
    api_averages: dict[str, float],
    active_sessions: int,
) -> None:
    """Generate system report HTML with error summary, API latency, and sessions.

    Maintains identical layout to original for downstream dependencies.
    """
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{active_sessions} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main orchestrator for the log processing pipeline."""
    # Ensure log file exists or seed with default values
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")

    # 1. Extract
    payload = extract_log_data(str(log_path))

    # 2. Transform
    transformed = transform_log_data(payload)

    # 3. Load to DB & Report
    load_data_to_db(
        DB_PATH, transformed["error_counts"], transformed["api_averages"]
    )

    generate_report(
        "report.html",
        transformed["error_counts"],
        transformed["api_averages"],
        transformed["active_sessions"],
    )

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
