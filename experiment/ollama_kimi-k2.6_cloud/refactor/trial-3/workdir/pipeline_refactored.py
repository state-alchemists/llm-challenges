"""Server log pipeline: Extract, Transform, Load (ETL) for metrics and reporting."""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LogEvent:
    """A single parsed log line."""

    dt: str
    level: str
    message: str


@dataclass
class TransformedData:
    """Aggregated metrics ready for load and report generation."""

    error_counts: dict[str, int] = field(default_factory=dict)
    api_latencies: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


def get_config() -> dict[str, str]:
    """Load runtime configuration from environment variables.

    Returns a mapping of all configurable values, using sensible defaults
    when a variable is not set.
    """
    return {
        "db_path": os.environ.get("DB_PATH", "metrics.db"),
        "log_file": os.environ.get("LOG_FILE", "server.log"),
        "db_host": os.environ.get("DB_HOST", "localhost"),
        "db_port": os.environ.get("DB_PORT", "5432"),
        "db_user": os.environ.get("DB_USER", "admin"),
        "db_pass": os.environ.get("DB_PASS", "password123"),
    }


def ensure_sample_log(log_path: str) -> None:
    """Create a sample log file if none exists at *log_path*."""
    if os.path.exists(log_path):
        return
    lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    with open(log_path, "w") as fh:
        fh.writelines(lines)


def extract(log_path: str) -> list[LogEvent]:
    """Parse the server log into structured events using regex.

    Expected line format::

        <YYYY-MM-DD HH:MM:SS> <LEVEL> <message...>

    Lines that do not match are skipped silently.
    """
    pattern = re.compile(
        r"^(?P<dt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
        r"(?P<level>ERROR|INFO|WARN)\s+"
        r"(?P<message>.*)$"
    )
    events: list[LogEvent] = []
    with open(log_path, "r") as fh:
        for line in fh:
            match = pattern.match(line.rstrip("\n"))
            if not match:
                continue
            events.append(
                LogEvent(
                    dt=match.group("dt"),
                    level=match.group("level"),
                    message=match.group("message"),
                )
            )
    return events


def transform(events: list[LogEvent]) -> TransformedData:
    """Aggregate extracted events into error counts, API latencies, and session state.

    * ERROR events increment *error_counts* by message text.
    * INFO "User …" events update *active_sessions*.
    * INFO "API … took …ms" events accumulate latency samples.
    * WARN events are parsed but not currently surfaced in the report.
    """
    data = TransformedData()
    user_pattern = re.compile(r"^User\s+(\d+)\s+(.+)$")
    api_pattern = re.compile(r"^API\s+(\S+)\s+took\s+(\d+)ms$")

    for event in events:
        if event.level == "ERROR":
            data.error_counts[event.message] = data.error_counts.get(event.message, 0) + 1
            continue

        if event.level == "WARN":
            # Parsed for parity with the original script, but not displayed.
            continue

        if event.level != "INFO":
            continue

        user_match = user_pattern.match(event.message)
        if user_match:
            uid = user_match.group(1)
            action = user_match.group(2)
            if "logged in" in action:
                data.active_sessions[uid] = event.dt
            elif "logged out" in action and uid in data.active_sessions:
                del data.active_sessions[uid]
            continue

        api_match = api_pattern.match(event.message)
        if api_match:
            endpoint = api_match.group(1)
            duration_ms = int(api_match.group(2))
            data.api_latencies.setdefault(endpoint, []).append(duration_ms)

    return data


def load(data: TransformedData, db_path: str) -> None:
    """Persist aggregated metrics to SQLite using parameterized queries.

    Creates the *errors* and *api_metrics* tables if they do not exist.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        for msg, count in data.error_counts.items():
            cursor.execute(
                "INSERT INTO errors VALUES (?, ?, ?)",
                (str(datetime.datetime.now()), msg, count),
            )

        for endpoint, times in data.api_latencies.items():
            avg = sum(times) / len(times)
            cursor.execute(
                "INSERT INTO api_metrics VALUES (?, ?, ?)",
                (str(datetime.datetime.now()), endpoint, avg),
            )

        conn.commit()


def generate_report(data: TransformedData, report_path: str) -> None:
    """Render an HTML report from the transformed metrics.

    The report contains three sections:
    1. Error Summary
    2. API Latency table
    3. Active session count
    """
    lines: list[str] = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]

    for err_msg, count in data.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")

    lines.extend([
        "</ul>",
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ])

    for endpoint, times in data.api_latencies.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(data.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    """Pipeline entry point: configure, extract, transform, load, and report."""
    config = get_config()
    ensure_sample_log(config["log_file"])
    print(f"Connecting to {config['db_host']}:{config['db_port']} as {config['db_user']}...")

    events = extract(config["log_file"])
    data = transform(events)
    load(data, config["db_path"])
    generate_report(data, "report.html")

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
