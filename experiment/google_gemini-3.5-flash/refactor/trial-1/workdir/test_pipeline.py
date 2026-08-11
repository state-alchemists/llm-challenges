import os
import unittest
import sqlite3
import tempfile
from pipeline import (
    LogEntry,
    LogTransformer,
    parse_log_line,
    extract_log_lines,
    load_metrics_to_db,
)


class TestPipeline(unittest.TestCase):
    """Unit tests for the refactored pipeline script."""

    def test_parse_log_line_valid_error(self) -> None:
        line = "2024-01-01 12:05:00 ERROR Database timeout\n"
        entry = parse_log_line(line)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.timestamp, "2024-01-01 12:05:00")
        self.assertEqual(entry.level, "ERROR")
        self.assertEqual(entry.message, "Database timeout")

    def test_parse_log_line_valid_info_user(self) -> None:
        line = "2024-01-01 12:00:00 INFO User 42 logged in"
        entry = parse_log_line(line)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.timestamp, "2024-01-01 12:00:00")
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.message, "User 42 logged in")

    def test_parse_log_line_invalid(self) -> None:
        line = "invalid line format"
        entry = parse_log_line(line)
        self.assertIsNone(entry)

    def test_log_transformer_errors(self) -> None:
        transformer = LogTransformer()
        entries = [
            LogEntry("2024-01-01 12:00:00", "ERROR", "Timeout"),
            LogEntry("2024-01-01 12:01:00", "ERROR", "Timeout"),
            LogEntry("2024-01-01 12:02:00", "ERROR", "Out of memory"),
        ]
        for e in entries:
            transformer.process_entry(e)

        self.assertEqual(transformer.errors["Timeout"], 2)
        self.assertEqual(transformer.errors["Out of memory"], 1)

    def test_log_transformer_sessions(self) -> None:
        transformer = LogTransformer()
        entries = [
            LogEntry("2024-01-01 12:00:00", "INFO", "User 42 logged in"),
            LogEntry("2024-01-01 12:01:00", "INFO", "User 99 logged in"),
            LogEntry("2024-01-01 12:02:00", "INFO", "User 42 logged out"),
        ]
        for e in entries:
            transformer.process_entry(e)

        self.assertNotIn("42", transformer.sessions)
        self.assertIn("99", transformer.sessions)
        self.assertEqual(transformer.sessions["99"], "2024-01-01 12:01:00")

    def test_log_transformer_api_calls(self) -> None:
        transformer = LogTransformer()
        entries = [
            LogEntry("2024-01-01 12:00:00", "INFO", "API /get took 100ms"),
            LogEntry("2024-01-01 12:01:00", "INFO", "API /get took 200ms"),
            LogEntry("2024-01-01 12:02:00", "INFO", "API /post took 50ms"),
        ]
        for e in entries:
            transformer.process_entry(e)

        self.assertEqual(transformer.endpoint_durations["/get"], [100, 200])
        self.assertEqual(transformer.endpoint_durations["/post"], [50])

    def test_extract_log_lines_missing(self) -> None:
        lines = extract_log_lines("non_existent_file.log")
        self.assertEqual(lines, [])

    def test_db_loading(self) -> None:
        # Create temporary DB file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_name = tmp.name

        try:
            errors = {"Some error": 5}
            endpoint_durations = {"/api": [100, 200]}

            load_metrics_to_db(tmp_name, errors, endpoint_durations)

            # Query temp db to verify
            conn = sqlite3.connect(tmp_name)
            cursor = conn.cursor()

            # Verify errors table
            cursor.execute("SELECT message, count FROM errors")
            err_rows = cursor.fetchall()
            self.assertEqual(len(err_rows), 1)
            self.assertEqual(err_rows[0], ("Some error", 5))

            # Verify api_metrics table
            cursor.execute("SELECT endpoint, avg_ms FROM api_metrics")
            metric_rows = cursor.fetchall()
            self.assertEqual(len(metric_rows), 1)
            self.assertEqual(metric_rows[0], ("/api", 150.0))

            conn.close()
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)


if __name__ == "__main__":
    unittest.main()
