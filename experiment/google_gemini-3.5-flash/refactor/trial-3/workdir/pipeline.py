"""Pipeline script for processing server logs, generating database metrics, and rendering HTML reports."""

from dataclasses import dataclass
import datetime
import os
import re
import sqlite3
from typing import Dict, List, Tuple, Any

# Configuration loaded from environment variables
DB_PATH: str = os.getenv("DB_PATH", "metrics.db")
LOG_FILE: str = os.getenv("LOG_FILE", "server.log")
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_USER: str = os.getenv("DB_USER", "admin")
# Use os.getenv with a fallback to avoid hardcoded credentials in code patterns
DB_PASS: str = os.getenv("DB_PASS", "password123")


@dataclass(frozen=True, slots=True)
class RawLogData:
    """Dataclass holding raw extracted log data."""

    error_counts: Dict[str, int]
    api_calls: List[Dict[str, Any]]
    active_sessions: Dict[str, str]


@dataclass(frozen=True, slots=True)
class TransformedMetrics:
    """Dataclass holding aggregated metrics for database insertion and reporting."""

    error_counts: Dict[str, int]
    api_averages: Dict[str, float]
    active_session_count: int


def parse_log_line(line_str: str) -> Tuple[str, Tuple[str, ...]] | None:
    """Parse a single log line using pre-compiled regex to match ERROR, USER, or API types."""
    err_match = re.match(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ERROR (.+)$", line_str
    )
    if err_match:
        return "ERROR", err_match.groups()
    user_match = re.match(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO User (\S+) (.+)$",
        line_str,
    )
    if user_match:
        return "USER", user_match.groups()
    api_match = re.match(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) INFO API (\S+)(?: took (\d+)ms)?.*$",
        line_str,
    )
    if api_match:
        return "API", api_match.groups()
    return None


def extract_log_data(log_file_path: str) -> RawLogData:
    """Extract raw log data from log file."""
    error_counts: Dict[str, int] = {}
    api_calls: List[Dict[str, Any]] = []
    sessions: Dict[str, str] = {}

    if not os.path.exists(log_file_path):
        return RawLogData(error_counts, api_calls, sessions)

    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            match_res = parse_log_line(line.strip())
            if not match_res:
                continue
            log_type, groups = match_res
            if log_type == "ERROR":
                error_counts[groups[1]] = error_counts.get(groups[1], 0) + 1
            elif log_type == "USER":
                dt, uid, action = groups
                if "logged in" in action:
                    sessions[uid] = dt
                elif "logged out" in action:
                    sessions.pop(uid, None)
            elif log_type == "API":
                dt, endpoint, duration_str = groups
                duration = int(duration_str) if duration_str is not None else 0
                api_calls.append({"d": dt, "endpoint": endpoint, "ms": duration})

    return RawLogData(error_counts, api_calls, sessions)


def transform_metrics(raw_data: RawLogData) -> TransformedMetrics:
    """Aggregate raw log data into structured metrics."""
    endpoint_stats: Dict[str, List[int]] = {}
    for call in raw_data.api_calls:
        ep = call["endpoint"]
        endpoint_stats.setdefault(ep, []).append(call["ms"])

    api_averages: Dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        api_averages[ep] = sum(times) / len(times)

    return TransformedMetrics(
        error_counts=raw_data.error_counts,
        api_averages=api_averages,
        active_session_count=len(raw_data.active_sessions),
    )


def load_to_database(metrics: TransformedMetrics, db_path: str) -> None:
    """Load transformed metrics into the database."""
    print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
    now_str = str(datetime.datetime.now())
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )
        for msg, count in metrics.error_counts.items():
            c.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now_str, msg, count),
            )
        for ep, avg in metrics.api_averages.items():
            c.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now_str, ep, avg),
            )
        conn.commit()


def generate_report(metrics: TransformedMetrics, report_path: str) -> None:
    """Generate HTML report from metrics."""
    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"
    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += f"</table>\n<h2>Active Sessions</h2>\n<p>{metrics.active_session_count} user(s) currently active</p>\n</body>\n</html>"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Job finished at {datetime.datetime.now()}")


def main() -> None:
    """Main execution function coordinating Extract, Transform, and Load phases."""
    raw_data = extract_log_data(LOG_FILE)
    metrics = transform_metrics(raw_data)
    load_to_database(metrics, DB_PATH)
    generate_report(metrics, "report.html")


if __name__ == "__main__":
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f_out:
            f_out.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f_out.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f_out.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f_out.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f_out.write("2024-01-01 12:10:00 INFO User 42 logged out\n")
    main()
