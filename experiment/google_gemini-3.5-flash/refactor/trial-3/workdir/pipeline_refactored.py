"""Log processing pipeline script.

Extracts, transforms, and loads server log information into a SQLite database
and generates a summary HTML report.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Any

# Configuration via environment variables with fallback defaults
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
DB_PASS: str = os.getenv("DB_PASS", "password123")


def extract_log_lines(log_file_path: str) -> list[dict[str, Any]]:
    """Extract raw log records from the log file using regex."""
    parsed_records: list[dict[str, Any]] = []
    if not os.path.exists(log_file_path):
        return parsed_records

    # Regex to parse timestamp, level, and message
    # e.g., "2024-01-01 12:00:00 INFO User 42 logged in"
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$"
    )

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = log_pattern.match(line)
            if match:
                dt, lvl, message = match.groups()
                parsed_records.append({
                    "dt": dt,
                    "level": lvl,
                    "message": message
                })
    return parsed_records


def transform_metrics(
    records: list[dict[str, Any]]
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, str]]:
    """Transform raw log records into structured aggregate statistics."""
    errors: dict[str, int] = {}
    latencies: dict[str, list[int]] = {}
    sessions: dict[str, str] = {}
    user_rx = re.compile(r"^User\s+(\S+)\s+(.+)$")
    api_rx = re.compile(r"^API\s+(\S+)(?:\s+took\s+(\d+)ms)?")

    for r in records:
        lvl, dt, msg = r["level"], r["dt"], r["message"]
        if lvl == "ERROR":
            errors[msg] = errors.get(msg, 0) + 1
        elif lvl == "INFO":
            if u_m := user_rx.match(msg):
                uid, act = u_m.groups()
                if "logged in" in act:
                    sessions[uid] = dt
                elif "logged out" in act and uid in sessions:
                    sessions.pop(uid)
            if a_m := api_rx.match(msg):
                ep, dur = a_m.groups()
                latencies.setdefault(ep, []).append(int(dur) if dur else 0)

    return errors, latencies, sessions


def load_to_database(
    db_path: str,
    errors: dict[str, int],
    latencies: dict[str, list[int]]
) -> None:
    """Load the transformed aggregate statistics into the SQLite database."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)")
        now = str(datetime.datetime.now())
        for msg, count in errors.items():
            c.execute("INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)", (now, msg, count))
        for ep, times in latencies.items():
            if times:
                c.execute(
                    "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                    (now, ep, sum(times) / len(times))
                )


def generate_html_report(
    report_path: str,
    errors: dict[str, int],
    latencies: dict[str, list[int]],
    sessions: dict[str, str]
) -> None:
    """Generate the HTML report from the aggregate statistics."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in errors.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, times in latencies.items():
        if times:
            avg = sum(times) / len(times)
            out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n<h2>Active Sessions</h2>\n"
    out += f"<p>{len(sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main orchestrator for the log processing pipeline."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    records = extract_log_lines(LOG_FILE)
    errors, latencies, sessions = transform_metrics(records)

    load_to_database(DB_PATH, errors, latencies)
    generate_html_report("report.html", errors, latencies, sessions)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
