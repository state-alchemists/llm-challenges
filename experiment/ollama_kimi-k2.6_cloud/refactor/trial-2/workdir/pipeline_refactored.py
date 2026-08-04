"""ETL pipeline that processes server logs and generates an HTML report.

Extract → Transform → Load flow:
1. Extract: read server logs and parse each line with regex.
2. Transform: aggregate error counts, API latency averages, and active sessions.
3. Load: persist metrics to SQLite with parameterized queries and write report.html.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path



@dataclass
class LogEntry:
    """A generic log entry after the base line has been split."""

    dt: str
    level: str
    message: str


@dataclass
class UserAction:
    """A parsed user action from an INFO log line."""

    dt: str
    user_id: str
    action: str


@dataclass
class ApiCall:
    """A parsed API call from an INFO log line."""

    dt: str
    endpoint: str
    ms: int


@dataclass
class ParsedLog:
    """Container for all data extracted from the log file."""

    errors: list[LogEntry] = field(default_factory=list)
    warnings: list[LogEntry] = field(default_factory=list)
    user_actions: list[UserAction] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)


@dataclass
class TransformedData:
    """Aggregated metrics ready for loading."""

    error_counts: dict[str, int]
    api_latency: dict[str, float]
    active_sessions: dict[str, str]


# Base log line: YYYY-MM-DD HH:MM:SS LEVEL message...
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (INFO|ERROR|WARN) (.*)$"
)
# User action inside an INFO message: User <id> <action...>
_USER_RE = re.compile(r"^User (\d+) (.+)$")
# API call inside an INFO message: API <endpoint> took <duration>ms
_API_RE = re.compile(r"^API (\S+) took (\d+)ms$")


def get_config() -> dict[str, str]:
    """Load configuration from environment variables.

    Returns a dictionary with the following keys:
        - db_path
        - log_file
        - db_host
        - db_port
        - db_user
        - db_password
    """
    return {
        "db_path": os.getenv("DB_PATH", "metrics.db"),
        "log_file": os.getenv("LOG_FILE", "server.log"),
        "db_host": os.getenv("DB_HOST", "localhost"),
        "db_port": os.getenv("DB_PORT", "5432"),
        "db_user": os.getenv("DB_USER", "admin"),
        "db_password": os.getenv("DB_PASSWORD", "password123"),
    }


def extract_logs(log_path: Path) -> ParsedLog:
    """Extract and parse server log lines using regex.

    Args:
        log_path: Path to the server log file.

    Returns:
        A ParsedLog container with errors, warnings, user actions, and API calls.
    """
    parsed = ParsedLog()

    if not log_path.exists():
        return parsed

    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            match = _LOG_LINE_RE.match(line)
            if not match:
                continue

            date_part, time_part, level, message = match.groups()
            dt = f"{date_part} {time_part}"

            if level == "ERROR":
                parsed.errors.append(LogEntry(dt=dt, level=level, message=message))
            elif level == "WARN":
                parsed.warnings.append(LogEntry(dt=dt, level=level, message=message))
            elif level == "INFO":
                user_match = _USER_RE.match(message)
                if user_match:
                    user_id, action = user_match.groups()
                    parsed.user_actions.append(
                        UserAction(dt=dt, user_id=user_id, action=action)
                    )
                    continue

                api_match = _API_RE.match(message)
                if api_match:
                    endpoint, duration_str = api_match.groups()
                    parsed.api_calls.append(
                        ApiCall(dt=dt, endpoint=endpoint, ms=int(duration_str))
                    )

    return parsed


def transform_data(parsed: ParsedLog) -> TransformedData:
    """Transform extracted log data into aggregated metrics.

    Args:
        parsed: The ParsedLog container from the extraction step.

    Returns:
        A TransformedData object with error counts, API latency, and active sessions.
    """
    error_counts: dict[str, int] = {}
    for entry in parsed.errors:
        error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in parsed.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.ms)

    api_latency = {
        ep: sum(times) / len(times) for ep, times in endpoint_times.items()
    }

    active_sessions: dict[str, str] = {}
    for action in parsed.user_actions:
        if "logged in" in action.action:
            active_sessions[action.user_id] = action.dt
        elif "logged out" in action.action and action.user_id in active_sessions:
            active_sessions.pop(action.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_latency=api_latency,
        active_sessions=active_sessions,
    )


def load_to_db(data: TransformedData, db_path: Path, config: dict[str, str]) -> None:
    """Load aggregated metrics into SQLite using parameterized queries.

    Args:
        data: The TransformedData object to persist.
        db_path: Path to the SQLite database file.
        config: Configuration dictionary (used for the connection banner).
    """
    print(
        f"Connecting to {config['db_host']}:{config['db_port']} as {config['db_user']}..."
    )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

        for msg, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (now, msg, count),
            )

        for ep, avg_ms in data.api_latency.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (now, ep, avg_ms),
            )

        conn.commit()


def generate_report(data: TransformedData, report_path: Path) -> None:
    """Generate an HTML report from the transformed metrics.

    Args:
        data: The TransformedData object to render.
        report_path: Path where the HTML report will be written.
    """
    lines: list[str] = []
    lines.append("<html>")
    lines.append("<head><title>System Report</title></head>")
    lines.append("<body>")

    lines.append("<h1>Error Summary</h1>")
    lines.append("<ul>")
    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")

    lines.append("<h2>API Latency</h2>")
    lines.append("<table border='1'>")
    lines.append("<tr><th>Endpoint</th><th>Avg (ms)</th></tr>")
    for ep, avg in data.api_latency.items():
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")
    lines.append("</table>")

    lines.append("<h2>Active Sessions</h2>")
    lines.append(f"<p>{len(data.active_sessions)} user(s) currently active</p>")

    lines.append("</body>")
    lines.append("</html>")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def _ensure_sample_log(log_path: Path) -> None:
    """Create a sample log file if one does not already exist."""
    if log_path.exists():
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in",
        "2024-01-01 12:05:00 ERROR Database timeout",
        "2024-01-01 12:05:05 ERROR Database timeout",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms",
        "2024-01-01 12:09:00 WARN Memory usage at 87%",
        "2024-01-01 12:10:00 INFO User 42 logged out",
    ]
    log_path.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")


def main() -> None:
    """Run the ETL pipeline end-to-end."""
    config = get_config()
    log_path = Path(config["log_file"])
    db_path = Path(config["db_path"])
    report_path = Path("report.html")

    _ensure_sample_log(log_path)

    parsed = extract_logs(log_path)
    data = transform_data(parsed)
    load_to_db(data, db_path, config)
    generate_report(data, report_path)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
