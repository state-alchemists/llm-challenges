"""Characterization tests for the refactored pipeline.

These tests pin down the behavior of ``pipeline_refactored`` against the
log fixture used by the challenge validator, plus the source-level security
properties the refactor was required to introduce.
"""

import re
import sqlite3
from pathlib import Path

import pytest

import pipeline_refactored as p

FIXTURE = (
    "2024-01-01 12:00:00 INFO User 42 logged in\n"
    "2024-01-01 12:05:00 ERROR Database timeout\n"
    "2024-01-01 12:05:05 ERROR Database timeout\n"
    "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
    "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
    "2024-01-01 12:10:00 INFO User 42 logged out\n"
)


@pytest.fixture()
def log_path(tmp_path: Path) -> Path:
    path = tmp_path / "server.log"
    path.write_text(FIXTURE, encoding="utf-8")
    return path


def fixture_data() -> p.ReportData:
    return p.ReportData(
        error_counts={"Database timeout": 2},
        endpoint_latencies={"/users/profile": [250]},
        active_sessions=0,
    )


# --- Extract ---------------------------------------------------------------


def test_extract_events_parses_every_fixture_line(log_path: Path) -> None:
    events = p.extract_events(log_path)
    assert [e.kind for e in events] == ["USER", "ERROR", "ERROR", "API", "WARN", "USER"]


def test_extract_events_captures_api_details(log_path: Path) -> None:
    api = next(e for e in p.extract_events(log_path) if e.kind == "API")
    assert api.endpoint == "/users/profile"
    assert api.duration_ms == 250


def test_extract_events_defaults_missing_duration_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "server.log"
    path.write_text("2024-01-01 12:08:00 INFO API /health\n", encoding="utf-8")
    api = next(e for e in p.extract_events(path) if e.kind == "API")
    assert api.duration_ms == 0


def test_extract_events_ignores_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "server.log"
    path.write_text("not a log line\nINFO User 1 logged in\n", encoding="utf-8")
    assert p.extract_events(path) == []


def test_extract_events_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert p.extract_events(tmp_path / "does-not-exist.log") == []


# --- Transform -------------------------------------------------------------


def test_transform_events_aggregates_fixture(log_path: Path) -> None:
    data = p.transform_events(p.extract_events(log_path))
    assert data.error_counts == {"Database timeout": 2}
    assert data.endpoint_latencies == {"/users/profile": [250]}
    assert data.active_sessions == 0


def test_transform_events_tracks_open_sessions() -> None:
    events = [
        p.LogEvent(
            "2024-01-01 12:00:00", "INFO", "USER", user_id="7", action="logged in"
        ),
        p.LogEvent(
            "2024-01-01 12:01:00", "INFO", "USER", user_id="9", action="logged in"
        ),
    ]
    assert p.transform_events(events).active_sessions == 2


# --- Load ------------------------------------------------------------------


def test_load_data_writes_parameterized_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    p.load_data(fixture_data(), db_path)

    with sqlite3.connect(db_path) as conn:
        errors = conn.execute("SELECT message, count FROM errors").fetchall()
        api = conn.execute("SELECT endpoint, avg_ms FROM api_metrics").fetchall()
    assert errors == [("Database timeout", 2)]
    assert api == [("/users/profile", 250.0)]


# --- Report ----------------------------------------------------------------


def test_generate_report_contains_expected_sections_and_data() -> None:
    html = p.generate_report(fixture_data()).lower()
    assert "error" in html
    assert "latency" in html
    assert "session" in html
    assert "database timeout" in html
    assert "/users/profile" in html
    assert "250" in html


def test_generate_report_matches_original_html() -> None:
    expected = (
        "<html>\n"
        "<head><title>System Report</title></head>\n"
        "<body>\n"
        "<h1>Error Summary</h1>\n"
        "<ul>\n"
        "<li><b>Database timeout</b>: 2 occurrences</li>\n"
        "</ul>\n"
        "<h2>API Latency</h2>\n"
        "<table border='1'>\n"
        "<tr><th>Endpoint</th><th>Avg (ms)</th></tr>\n"
        "<tr><td>/users/profile</td><td>250.0</td></tr>\n"
        "</table>\n"
        "<h2>Active Sessions</h2>\n"
        "<p>0 user(s) currently active</p>\n"
        "</body>\n"
        "</html>"
    )
    assert p.generate_report(fixture_data()) == expected


# --- Config ----------------------------------------------------------------


def test_load_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE", "/tmp/x.log")
    monkeypatch.setenv("DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("DB_HOST", "db.example.com")
    monkeypatch.setenv("DB_PORT", "9999")
    monkeypatch.setenv("DB_USER", "svc")
    monkeypatch.setenv("DB_PASS", "hunter2")
    cfg = p.load_config()
    assert cfg.log_path == Path("/tmp/x.log")
    assert cfg.db_path == Path("/tmp/x.db")
    assert cfg.db_host == "db.example.com"
    assert cfg.db_port == 9999
    assert cfg.db_user == "svc"
    assert cfg.db_pass == "hunter2"


def test_load_config_has_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LOG_FILE",
        "DB_PATH",
        "REPORT_PATH",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASS",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = p.load_config()
    assert cfg.log_path == Path("server.log")
    assert cfg.db_path == Path("metrics.db")
    assert cfg.report_path == Path("report.html")


# --- End to end ------------------------------------------------------------


def test_main_runs_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOG_FILE", "server.log")
    monkeypatch.setenv("DB_PATH", "metrics.db")
    (tmp_path / "server.log").write_text(FIXTURE, encoding="utf-8")

    p.main()

    html = (tmp_path / "report.html").read_text(encoding="utf-8").lower()
    assert "database timeout" in html
    assert "/users/profile" in html
    assert "session" in html
    assert (tmp_path / "metrics.db").is_file()


# --- Source-level security properties -------------------------------------


def test_source_has_no_hardcoded_credential() -> None:
    source = Path(p.__file__).read_text(encoding="utf-8")
    assert "password123" not in source


def test_source_has_no_sql_interpolation() -> None:
    source = Path(p.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        if "execute(" in line.lower():
            assert not re.search(r"execute\s*\(.*%[sdf]", line), line
            assert not re.search(r"execute\s*\(.*\+", line), line
            assert not re.search(r'execute\s*\(f["\']', line), line


def test_source_uses_environment_variables_for_config() -> None:
    source = Path(p.__file__).read_text(encoding="utf-8")
    assert "os.getenv" in source
