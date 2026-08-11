"""Tests for the refactored pipeline.py script."""

import os
from pathlib import Path
import sqlite3
import pytest

from pipeline import (
    DB_HOST,
    DB_PASS,
    DB_PATH,
    DB_PORT,
    DB_USER,
    LOG_FILE,
    ApiCallEvent,
    ErrorEvent,
    ExtractedData,
    UserSessionEvent,
    WarnEvent,
    extract_logs,
    generate_report_html,
    load_to_database,
    parse_log_line,
    run_pipeline,
    transform_data,
)


def test_default_env_configs():
    """Verifies that defaults are loaded correctly."""
    assert DB_PATH == "metrics.db"
    assert LOG_FILE == "server.log"
    assert DB_HOST == "localhost"
    assert DB_PORT == 5432
    assert DB_USER == "admin"
    assert DB_PASS == "password123"


def test_parse_log_line_error():
    """Tests parsing of an ERROR log line."""
    line = "2024-01-01 12:05:00 ERROR Database timeout occurred"
    event = parse_log_line(line)
    assert isinstance(event, ErrorEvent)
    assert event.timestamp == "2024-01-01 12:05:00"
    assert event.message == "Database timeout occurred"


def test_parse_log_line_warn():
    """Tests parsing of a WARN log line."""
    line = "2024-01-01 12:09:00 WARN Memory usage at 87%"
    event = parse_log_line(line)
    assert isinstance(event, WarnEvent)
    assert event.timestamp == "2024-01-01 12:09:00"
    assert event.message == "Memory usage at 87%"


def test_parse_log_line_user_login():
    """Tests parsing of an INFO log line for user login."""
    line = "2024-01-01 12:00:00 INFO User 42 logged in"
    event = parse_log_line(line)
    assert isinstance(event, UserSessionEvent)
    assert event.timestamp == "2024-01-01 12:00:00"
    assert event.user_id == "42"
    assert event.action == "logged in"


def test_parse_log_line_api_call():
    """Tests parsing of an INFO log line for an API call with duration."""
    line = "2024-01-01 12:08:00 INFO API /users/profile took 250ms"
    event = parse_log_line(line)
    assert isinstance(event, ApiCallEvent)
    assert event.timestamp == "2024-01-01 12:08:00"
    assert event.endpoint == "/users/profile"
    assert event.duration_ms == 250


def test_parse_log_line_api_call_no_duration():
    """Tests parsing of an INFO log line for an API call without duration."""
    line = "2024-01-01 12:08:00 INFO API /users/profile"
    event = parse_log_line(line)
    assert isinstance(event, ApiCallEvent)
    assert event.timestamp == "2024-01-01 12:08:00"
    assert event.endpoint == "/users/profile"
    assert event.duration_ms == 0


def test_parse_invalid_log_line():
    """Tests that malformed or unrecognized log lines return None."""
    assert parse_log_line("invalid line") is None
    assert parse_log_line("2024-01-01 12:00:00 DEBUG Verbose debug message") is None


def test_extract_logs_nonexistent_file():
    """Tests extraction behavior when log file does not exist."""
    data = extract_logs("nonexistent_log_file.log")
    assert isinstance(data, ExtractedData)
    assert len(data.errors) == 0
    assert len(data.warnings) == 0
    assert len(data.user_sessions) == 0
    assert len(data.api_calls) == 0


def test_transform_data():
    """Tests processing and aggregating of extracted log data."""
    extracted = ExtractedData(
        errors=[
            ErrorEvent("2024-01-01 12:05:00", "DB Error"),
            ErrorEvent("2024-01-01 12:05:05", "DB Error"),
            ErrorEvent("2024-01-01 12:06:00", "Timeout Error"),
        ],
        warnings=[WarnEvent("2024-01-01 12:09:00", "Memory warning")],
        user_sessions=[
            UserSessionEvent("2024-01-01 12:00:00", "abc", "logged in"),
            UserSessionEvent("2024-01-01 12:01:00", "def", "logged in"),
            UserSessionEvent("2024-01-01 12:02:00", "abc", "logged out"),
        ],
        api_calls=[
            ApiCallEvent("2024-01-01 12:08:00", "/home", 100),
            ApiCallEvent("2024-01-01 12:08:10", "/home", 200),
            ApiCallEvent("2024-01-01 12:08:20", "/users", 300),
        ],
    )

    transformed = transform_data(extracted)

    assert transformed.error_counts == {"DB Error": 2, "Timeout Error": 1}
    assert transformed.api_latencies == {"/home": [100, 200], "/users": [300]}
    assert list(transformed.active_sessions.keys()) == ["def"]
    assert transformed.active_sessions["def"] == "2024-01-01 12:01:00"


def test_sql_injection_defense(tmp_path):
    """Verifies that parameterized queries are used and prevent SQL injection.

    If inputs containing SQL injection are used, they should be safely treated as
    strings and inserted correctly without causing syntax errors or database
    corruption.
    """
    db_file = tmp_path / "test_injection.db"
    malicious_msg = "test_msg'); DROP TABLE errors; --"
    transformed = ExtractedData(
        errors=[ErrorEvent("2024-01-01 12:00:00", malicious_msg)],
        warnings=[],
        user_sessions=[],
        api_calls=[],
    )
    metrics = transform_data(transformed)

    # Perform load step
    load_to_database(
        transformed=metrics,
        db_path=str(db_file),
        db_host="localhost",
        db_port=1234,
        db_user="test_user",
    )

    # Check that database still has the table and the row is entered safely
    conn = sqlite3.connect(str(db_file))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT message, count FROM errors")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == malicious_msg
        assert rows[0][1] == 1
    finally:
        conn.close()


def test_complete_pipeline_run(tmp_path):
    """Performs an integration test of the complete pipeline with a custom environment."""
    log_file = tmp_path / "server_test.log"
    db_file = tmp_path / "metrics_test.db"
    report_file = tmp_path / "report_test.html"

    # Create dummy log content
    log_content = (
        "2024-01-01 12:00:00 INFO User 101 logged in\n"
        "2024-01-01 12:01:00 INFO API /api/v1/test took 150ms\n"
        "2024-01-01 12:02:00 ERROR Out of memory\n"
    )
    log_file.write_text(log_content, encoding="utf-8")

    # Run pipeline with explicit paths
    extracted = extract_logs(str(log_file))
    transformed = transform_data(extracted)

    load_to_database(
        transformed=transformed,
        db_path=str(db_file),
        db_host="127.0.0.1",
        db_port=5432,
        db_user="admin",
    )
    generate_report_html(transformed, str(report_file))

    # Assert database load correctness
    conn = sqlite3.connect(str(db_file))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT message, count FROM errors")
        errors = cursor.fetchall()
        assert errors == [("Out of memory", 1)]

        cursor.execute("SELECT endpoint, avg_ms FROM api_metrics")
        api_metrics = cursor.fetchall()
        assert api_metrics == [("/api/v1/test", 150.0)]
    finally:
        conn.close()

    # Assert report correctness
    report_content = report_file.read_text(encoding="utf-8")
    assert "Out of memory" in report_content
    assert "/api/v1/test" in report_content
    assert "1 user(s) currently active" in report_content
