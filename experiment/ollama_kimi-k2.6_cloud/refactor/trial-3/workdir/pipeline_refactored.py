"""Server log ETL pipeline.

Reads server logs, extracts metrics, loads them into SQLite, and writes an HTML report.
"""

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""
    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str
    level: str
    message: str = ""
    user_id: str = ""
    action: str = ""
    endpoint: str = ""
    duration_ms: int = 0


@dataclass
class TransformedData:
    """Aggregated data ready for load and reporting."""
    error_counts: dict[str, int] = field(default_factory=dict)
    api_stats: dict[str, list[int]] = field(default_factory=dict)
    active_sessions: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

# Base pattern:  YYYY-MM-DD HH:MM:SS LEVEL remainder
_BASE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (ERROR|INFO|WARN) (.*)$"
)

# INFO sub-patterns
_USER_RE = re.compile(r"^User (\d+) (.+)$")
_API_RE = re.compile(r"^API (\S+)(?: took (\d+)ms)?$")


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a :class:`LogEntry`.

    Returns ``None`` if the line does not match the expected format.
    """
    line = line.strip()
    if not line:
        return None

    m = _BASE_RE.match(line)
    if not m:
        return None

    timestamp, level, payload = m.groups()
    entry = LogEntry(timestamp=timestamp, level=level)

    if level in ("ERROR", "WARN"):
        entry.message = payload
        return entry

    if level == "INFO":
        user_m = _USER_RE.match(payload)
        if user_m:
            entry.user_id = user_m.group(1)
            entry.action = user_m.group(2)
            return entry

        api_m = _API_RE.match(payload)
        if api_m:
            entry.endpoint = api_m.group(1)
            entry.duration_ms = int(api_m.group(2)) if api_m.group(2) else 0
            return entry

    # Unrecognised INFO line – ignore
    return None


def extract(log_file: str) -> list[LogEntry]:
    """Read *log_file* and return a list of parsed :class:`LogEntry` objects."""
    entries: list[LogEntry] = []
    with open(log_file, "r", encoding="utf-8") as fh:
        for line in fh:
            entry = parse_log_line(line)
            if entry is not None:
                entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(entries: list[LogEntry]) -> TransformedData:
    """Aggregate raw log entries into error counts, API latency stats, and session state.

    The original pipeline preserved WARN lines in the intermediate list but never
    surfaced them in the report or DB; this implementation keeps the same visible
    behaviour by tracking only ERROR items for the error summary.
    """
    data = TransformedData()

    for entry in entries:
        if entry.level == "ERROR":
            data.error_counts[entry.message] = data.error_counts.get(entry.message, 0) + 1

        elif entry.level == "INFO" and entry.user_id:
            if "logged in" in entry.action:
                data.active_sessions[entry.user_id] = entry.timestamp
            elif "logged out" in entry.action and entry.user_id in data.active_sessions:
                data.active_sessions.pop(entry.user_id)

        elif entry.level == "INFO" and entry.endpoint:
            data.api_stats.setdefault(entry.endpoint, []).append(entry.duration_ms)

        # WARN is parsed but intentionally not surfaced, matching legacy behaviour.

    return data


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load(data: TransformedData, config: Config) -> None:
    """Persist aggregated metrics to the SQLite database at *config.db_path*.

    Uses parameterized queries to eliminate SQL-injection risk.
    """
    print(f"Connecting to {config.db_host}:{config.db_port} as {config.db_user}...")

    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
    )

    now = str(datetime.datetime.now())

    for msg, count in data.error_counts.items():
        cursor.execute(
            "INSERT INTO errors VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, times in data.api_stats.items():
        avg = sum(times) / len(times)
        cursor.execute(
            "INSERT INTO api_metrics VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(data: TransformedData, report_path: str) -> None:
    """Write an HTML report summarising errors, API latency, and active sessions."""
    lines = [
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

    for ep, times in data.api_stats.items():
        avg = sum(times) / len(times)
        lines.append(f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>")

    lines.extend([
        "</table>",
        "<h2>Active Sessions</h2>",
        f"<p>{len(data.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ])

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _getenv(key: str, default: str) -> str:
    """Return the environment variable *key* or *default*."""
    return os.environ.get(key, default)


def load_config() -> Config:
    """Build a :class:`Config` from environment variables.

    Falls back to the legacy hard-coded defaults so the script remains
    runnable out-of-the-box when the variables are not set.
    """
    return Config(
        db_path=_getenv("DB_PATH", "metrics.db"),
        log_file=_getenv("LOG_FILE", "server.log"),
        db_host=_getenv("DB_HOST", "localhost"),
        db_port=int(_getenv("DB_PORT", "5432")),
        db_user=_getenv("DB_USER", "admin"),
        db_pass=_getenv("DB_PASS", "password123"),
    )


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _create_dummy_log(log_file: str) -> None:
    """Create a minimal log file for local testing."""
    with open(log_file, "w", encoding="utf-8") as fh:
        fh.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
        fh.write("2024-01-01 12:05:00 ERROR Database timeout\n")
        fh.write("2024-01-01 12:05:05 ERROR Database timeout\n")
        fh.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
        fh.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
        fh.write("2024-01-01 12:10:00 INFO User 42 logged out\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full ETL pipeline."""
    config = load_config()

    if not os.path.exists(config.log_file):
        _create_dummy_log(config.log_file)

    entries = extract(config.log_file)
    data = transform(entries)
    load(data, config)
    generate_report(data, "report.html")
    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
