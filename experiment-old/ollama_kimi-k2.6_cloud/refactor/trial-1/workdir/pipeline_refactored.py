"""Server log processor: Extracts metrics from logs, persists them to SQLite,
and generates an HTML report."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    log_file: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str

    @classmethod
    def from_env(cls) -> Config:
        """Build configuration from environment variables with sensible defaults."""
        return cls(
            db_path=os.getenv("DB_PATH", "metrics.db"),
            log_file=os.getenv("LOG_FILE", "server.log"),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", "admin"),
            db_pass=os.getenv("DB_PASS", "password123"),
        )


@dataclass
class ErrorEntry:
    """A single ERROR or WARN log line."""

    dt: str
    level: str
    message: str


@dataclass
class SessionEvent:
    """A user login or logout event."""

    dt: str
    user_id: str
    action: str


@dataclass
class APICall:
    """An API latency record."""

    dt: str
    endpoint: str
    ms: int


@dataclass
class ExtractedData:
    """Container for all parsed log entries."""

    errors: list[ErrorEntry] = field(default_factory=list)
    sessions: list[SessionEvent] = field(default_factory=list)
    api_calls: list[APICall] = field(default_factory=list)


# Pre-compiled regex patterns for each expected log shape.
_LOG_DT = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
_RE_ERROR = re.compile(rf"^{_LOG_DT} ERROR (.*)$")
_RE_WARN = re.compile(rf"^{_LOG_DT} WARN (.*)$")
_RE_USER = re.compile(rf"^{_LOG_DT} INFO User (\S+) (.*)$")
_RE_API = re.compile(rf"^{_LOG_DT} INFO API (\S+) took (\d+)ms$")


def extract(log_file: str | Path) -> ExtractedData:
    """Parse the server log file into structured records.

    Args:
        log_file: Path to the log file to read.

    Returns:
        An :class:`ExtractedData` instance holding errors, session events,
        and API calls.
    """
    data = ExtractedData()
    path = Path(log_file)

    if not path.exists():
        return data

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue

            if match := _RE_ERROR.match(line):
                dt, message = match.groups()
                data.errors.append(ErrorEntry(dt=dt, level="ERROR", message=message))
            elif match := _RE_WARN.match(line):
                dt, message = match.groups()
                data.errors.append(ErrorEntry(dt=dt, level="WARN", message=message))
            elif match := _RE_USER.match(line):
                dt, user_id, action = match.groups()
                data.sessions.append(SessionEvent(dt=dt, user_id=user_id, action=action))
            elif match := _RE_API.match(line):
                dt, endpoint, ms = match.groups()
                data.api_calls.append(APICall(dt=dt, endpoint=endpoint, ms=int(ms)))

    return data


@dataclass
class TransformedData:
    """Aggregated metrics ready for persistence and reporting."""

    error_counts: dict[str, int]
    api_avg_ms: dict[str, float]
    active_sessions: dict[str, str]


def transform(data: ExtractedData) -> TransformedData:
    """Aggregate extracted log records into summary metrics.

    Args:
        data: Parsed log records from :func:`extract`.

    Returns:
        Aggregated error counts, per-endpoint API latency averages, and
        the set of currently active user sessions.
    """
    error_counts: dict[str, int] = {}
    for entry in data.errors:
        if entry.level == "ERROR":
            error_counts[entry.message] = error_counts.get(entry.message, 0) + 1

    endpoint_times: dict[str, list[int]] = {}
    for call in data.api_calls:
        endpoint_times.setdefault(call.endpoint, []).append(call.ms)

    api_avg_ms = {
        endpoint: sum(times) / len(times)
        for endpoint, times in endpoint_times.items()
    }

    active_sessions: dict[str, str] = {}
    for event in data.sessions:
        if "logged in" in event.action:
            active_sessions[event.user_id] = event.dt
        elif "logged out" in event.action and event.user_id in active_sessions:
            active_sessions.pop(event.user_id)

    return TransformedData(
        error_counts=error_counts,
        api_avg_ms=api_avg_ms,
        active_sessions=active_sessions,
    )


def load(
    config: Config,
    metrics: TransformedData,
    output_html: str | Path = "report.html",
) -> None:
    """Persist metrics to SQLite and write the HTML report.

    Args:
        config: Runtime configuration (includes DB path and credentials).
        metrics: Aggregated metrics from :func:`transform`.
        output_html: Destination path for the generated report.
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

    now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    for msg, count in metrics.error_counts.items():
        cursor.execute(
            "INSERT INTO errors (dt, message, count) VALUES (?, ?, ?)",
            (now, msg, count),
        )

    for endpoint, avg in metrics.api_avg_ms.items():
        cursor.execute(
            "INSERT INTO api_metrics (dt, endpoint, avg_ms) VALUES (?, ?, ?)",
            (now, endpoint, avg),
        )

    conn.commit()
    conn.close()

    html = _build_html_report(metrics)
    Path(output_html).write_text(html, encoding="utf-8")

    print(f"Job finished at {datetime.datetime.now()}")


def _build_html_report(metrics: TransformedData) -> str:
    """Render an HTML report from aggregated metrics."""
    lines = [
        "<html>",
        "<head><title>System Report</title></head>",
        "<body>",
        "<h1>Error Summary</h1>",
        "<ul>",
    ]
    for err_msg, count in metrics.error_counts.items():
        lines.append(f"<li><b>{err_msg}</b>: {count} occurrences</li>")
    lines.append("</ul>")
    lines.append("")

    lines += [
        "<h2>API Latency</h2>",
        "<table border='1'>",
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>",
    ]
    for endpoint, avg in metrics.api_avg_ms.items():
        lines.append(f"<tr><td>{endpoint}</td><td>{round(avg, 1)}</td></tr>")
    lines += [
        "</table>",
        "",
        "<h2>Active Sessions</h2>",
        f"<p>{len(metrics.active_sessions)} user(s) currently active</p>",
        "</body>",
        "</html>",
    ]

    return "\n".join(lines)


def _ensure_sample_log(log_file: str | Path) -> None:
    """Create a sample log file if one does not already exist."""
    path = Path(log_file)
    if path.exists():
        return

    sample_lines = [
        "2024-01-01 12:00:00 INFO User 42 logged in\n",
        "2024-01-01 12:05:00 ERROR Database timeout\n",
        "2024-01-01 12:05:05 ERROR Database timeout\n",
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n",
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n",
        "2024-01-01 12:10:00 INFO User 42 logged out\n",
    ]
    path.write_text("".join(sample_lines), encoding="utf-8")


def main() -> None:
    """Orchestrate the ETL pipeline."""
    config = Config.from_env()
    _ensure_sample_log(config.log_file)

    raw = extract(config.log_file)
    metrics = transform(raw)
    load(config, metrics)


if __name__ == "__main__":
    main()
