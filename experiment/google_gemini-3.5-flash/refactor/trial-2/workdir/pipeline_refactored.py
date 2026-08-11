import datetime
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# --- Configuration & Environment Variables ---
DB_PATH = Path(os.getenv("DB_PATH", "metrics.db"))
LOG_FILE = Path(os.getenv("LOG_FILE", "server.log"))
REPORT_FILE = Path(os.getenv("REPORT_FILE", "report.html"))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "password123")


# --- Data Structures ---
@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """Represents an error log entry."""
    dt: str
    message: str


@dataclass(frozen=True, slots=True)
class UserEntry:
    """Represents a user session log entry."""
    dt: str
    user_id: str
    action: str


@dataclass(frozen=True, slots=True)
class ApiEntry:
    """Represents an API latency log entry."""
    dt: str
    endpoint: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class WarnEntry:
    """Represents a warning log entry."""
    dt: str
    message: str


@dataclass(frozen=True, slots=True)
class ExtractedLogData:
    """Container for all parsed log entries."""
    errors: list[ErrorEntry]
    users: list[UserEntry]
    apis: list[ApiEntry]
    warns: list[WarnEntry]


@dataclass(frozen=True, slots=True)
class TransformedMetrics:
    """Container for processed and aggregated log metrics."""
    error_counts: dict[str, int]
    api_averages: dict[str, float]
    active_sessions: dict[str, str]


# --- Regular Expressions ---
# Matches standard log header format: YYYY-MM-DD HH:MM:SS LEVEL message
LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$"
)

# Matches user action log format: "User <uid> <action>"
USER_LOG_RE = re.compile(r"User\s+(\S+)\s+(.+)$")

# Matches API latency log format: "API <endpoint> [took <ms>ms]"
API_LOG_RE = re.compile(r"API\s+(\S+)(?:\s+took\s+(\d+)ms)?")


# --- Phase 1: Extract ---
def extract_log_data(file_path: Path) -> ExtractedLogData:
    """Reads the raw log file and parses each line using regular expressions.

    Args:
        file_path: Path to the log file.

    Returns:
        An ExtractedLogData containing categorized lists of parsed entries.
    """
    errors: list[ErrorEntry] = []
    users: list[UserEntry] = []
    apis: list[ApiEntry] = []
    warns: list[WarnEntry] = []

    if not file_path.exists():
        return ExtractedLogData(errors, users, apis, warns)

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = LOG_LINE_RE.match(line)
            if not match:
                continue

            date_str, time_str, lvl, content = match.groups()
            dt = f"{date_str} {time_str}"
            content = content.strip()

            if lvl == "ERROR":
                errors.append(ErrorEntry(dt=dt, message=content))

            elif lvl == "INFO" and "User" in line:
                user_match = USER_LOG_RE.search(content)
                if user_match:
                    uid = user_match.group(1)
                    action = user_match.group(2).strip()
                    users.append(UserEntry(dt=dt, user_id=uid, action=action))

            elif lvl == "INFO" and "API" in line:
                api_match = API_LOG_RE.search(content)
                if api_match:
                    endpoint = api_match.group(1)
                    dur_str = api_match.group(2)
                    dur = int(dur_str) if dur_str is not None else 0
                    apis.append(ApiEntry(dt=dt, endpoint=endpoint, duration_ms=dur))

            elif lvl == "WARN":
                warns.append(WarnEntry(dt=dt, message=content))

    return ExtractedLogData(errors, users, apis, warns)


# --- Phase 2: Transform ---
def transform_errors(errors: list[ErrorEntry]) -> dict[str, int]:
    """Calculates occurrence counts for each unique error message."""
    counts: dict[str, int] = {}
    for err in errors:
        counts[err.message] = counts.get(err.message, 0) + 1
    return counts


def transform_api_metrics(apis: list[ApiEntry]) -> dict[str, float]:
    """Calculates the average duration in ms for each unique API endpoint."""
    endpoint_stats: dict[str, list[int]] = {}
    for api in apis:
        endpoint_stats.setdefault(api.endpoint, []).append(api.duration_ms)

    averages: dict[str, float] = {}
    for ep, times in endpoint_stats.items():
        averages[ep] = sum(times) / len(times) if times else 0.0
    return averages


def transform_active_sessions(users: list[UserEntry]) -> dict[str, str]:
    """Processes user events sequentially to track currently active sessions."""
    sessions: dict[str, str] = {}
    for user in users:
        if "logged in" in user.action:
            sessions[user.user_id] = user.dt
        elif "logged out" in user.action and user.user_id in sessions:
            sessions.pop(user.user_id)
    return sessions


def transform_log_data(extracted: ExtractedLogData) -> TransformedMetrics:
    """Aggregates and formats raw parsed data into target metrics.

    Args:
        extracted: The parsed raw log records.

    Returns:
        A TransformedMetrics object containing structured statistics.
    """
    return TransformedMetrics(
        error_counts=transform_errors(extracted.errors),
        api_averages=transform_api_metrics(extracted.apis),
        active_sessions=transform_active_sessions(extracted.users),
    )


# --- Phase 3: Load ---
def load_to_database(
    db_path: Path,
    metrics: TransformedMetrics,
    db_host: str,
    db_port: int,
    db_user: str,
) -> None:
    """Saves the aggregated metrics into the SQLite database.

    Uses parameterized queries to protect against SQL injection.

    Args:
        db_path: Path to the SQLite database file.
        metrics: The TransformedMetrics object with aggregated data.
        db_host: Hostname of the database server (for logging).
        db_port: Port of the database server (for logging).
        db_user: User of the database server (for logging).
    """
    print(f"Connecting to {db_host}:{db_port} as {db_user}...")

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS errors (dt TEXT, message TEXT, count INTEGER)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS api_metrics (dt TEXT, endpoint TEXT, avg_ms REAL)"
        )

        current_time = str(datetime.datetime.now())

        for msg, count in metrics.error_counts.items():
            cursor.execute(
                "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
                (current_time, msg, count),
            )

        for ep, avg in metrics.api_averages.items():
            cursor.execute(
                "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
                (current_time, ep, avg),
            )

        conn.commit()
    finally:
        conn.close()


def load_to_html_report(report_path: Path, metrics: TransformedMetrics) -> None:
    """Generates an HTML report document from the aggregated metrics.

    Args:
        report_path: Path where the HTML file should be written.
        metrics: The TransformedMetrics object with aggregated data.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)

    out = "<html>\n<head><title>System Report</title></head>\n<body>\n"

    out += "<h1>Error Summary</h1>\n<ul>\n"
    for err_msg, count in metrics.error_counts.items():
        out += f"<li><b>{err_msg}</b>: {count} occurrences</li>\n"
    out += "</ul>\n"

    out += "<h2>API Latency</h2>\n<table border='1'>\n"
    out += "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
    for ep, avg in metrics.api_averages.items():
        out += f"<tr><td>{ep}</td><td>{round(avg, 1)}</td></tr>\n"
    out += "</table>\n"

    out += "<h2>Active Sessions</h2>\n"
    out += f"<p>{len(metrics.active_sessions)} user(s) currently active</p>\n"
    out += "</body>\n</html>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    """Main execution orchestrator of the pipeline script."""
    # Ensure raw log file exists for demo purposes
    if not LOG_FILE.exists():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("2024-01-01 12:00:00 INFO User 42 logged in\n")
            f.write("2024-01-01 12:05:00 ERROR Database timeout\n")
            f.write("2024-01-01 12:05:05 ERROR Database timeout\n")
            f.write("2024-01-01 12:08:00 INFO API /users/profile took 250ms\n")
            f.write("2024-01-01 12:09:00 WARN Memory usage at 87%\n")
            f.write("2024-01-01 12:10:00 INFO User 42 logged out\n")

    # Extract
    extracted = extract_log_data(LOG_FILE)

    # Transform
    metrics = transform_log_data(extracted)

    # Load
    load_to_database(
        db_path=DB_PATH,
        metrics=metrics,
        db_host=DB_HOST,
        db_port=DB_PORT,
        db_user=DB_USER,
    )

    load_to_html_report(REPORT_FILE, metrics)

    print(f"Job finished at {datetime.datetime.now()}")


if __name__ == "__main__":
    main()
