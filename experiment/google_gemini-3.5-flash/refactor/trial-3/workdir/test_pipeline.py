import os
import sqlite3
import subprocess
import unittest
from pathlib import Path


class TestPipelineRefactor(unittest.TestCase):
    def setUp(self):
        self.db_path = Path("metrics.db")
        self.log_path = Path("server.log")
        self.report_path = Path("report.html")

        # Clean up any existing files before run
        for p in [self.db_path, self.log_path, self.report_path]:
            if p.exists():
                p.unlink()

    def tearDown(self):
        # Clean up files generated during test
        for p in [self.db_path, self.log_path, self.report_path]:
            if p.exists():
                p.unlink()

    def test_pipeline_output(self):
        # Run the refactored script. We will test running pipeline.py.
        # It should generate a default server.log if none exists,
        # then process it to create metrics.db and report.html.
        result = subprocess.run(
            ["python3", "pipeline.py"],
            capture_output=True,
            text=True,
            check=True
        )

        # Assert outputs exist
        self.assertTrue(self.log_path.exists(), "server.log should be created")
        self.assertTrue(self.db_path.exists(), "metrics.db should be created")
        self.assertTrue(self.report_path.exists(), "report.html should be created")

        # Verify HTML content
        report_content = self.report_path.read_text(encoding="utf-8")
        self.assertIn("<h1>Error Summary</h1>", report_content)
        self.assertIn("<b>Database timeout</b>: 2 occurrences", report_content)
        self.assertIn("<h2>API Latency</h2>", report_content)
        self.assertIn("<td>/users/profile</td><td>250.0</td>", report_content)
        self.assertIn("<h2>Active Sessions</h2>", report_content)
        self.assertIn("<p>0 user(s) currently active</p>", report_content)

        # Verify SQLite DB
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            errors = cursor.execute("SELECT message, count FROM errors").fetchall()
            self.assertEqual(errors, [("Database timeout", 2)])

            api_metrics = cursor.execute("SELECT endpoint, avg_ms FROM api_metrics").fetchall()
            self.assertEqual(api_metrics, [("/users/profile", 250.0)])
        finally:
            conn.close()

    def test_pipeline_env_config(self):
        custom_db = Path("custom_metrics.db")
        custom_log = Path("custom_server.log")

        for p in [custom_db, custom_log]:
            if p.exists():
                p.unlink()

        # Create custom log
        custom_log.write_text(
            "2024-01-01 12:00:00 ERROR Custom error message\n"
            "2024-01-01 12:05:00 INFO API /custom/path took 100ms\n"
            "2024-01-01 12:06:00 INFO User 123 logged in\n",
            encoding="utf-8"
        )

        try:
            env = os.environ.copy()
            env["DB_PATH"] = str(custom_db)
            env["LOG_FILE"] = str(custom_log)

            result = subprocess.run(
                ["python3", "pipeline.py"],
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            self.assertTrue(custom_db.exists(), "Custom DB should be created")
            self.assertFalse(self.db_path.exists(), "Default DB should not be created")

            # Verify SQLite DB
            conn = sqlite3.connect(custom_db)
            try:
                cursor = conn.cursor()
                errors = cursor.execute("SELECT message, count FROM errors").fetchall()
                self.assertEqual(errors, [("Custom error message", 1)])

                api_metrics = cursor.execute("SELECT endpoint, avg_ms FROM api_metrics").fetchall()
                self.assertEqual(api_metrics, [("/custom/path", 100.0)])
            finally:
                conn.close()

            # Verify HTML report (uses hardcoded report.html but we check active sessions = 1)
            report_content = self.report_path.read_text(encoding="utf-8")
            self.assertIn("<p>1 user(s) currently active</p>", report_content)

        finally:
            for p in [custom_db, custom_log]:
                if p.exists():
                    p.unlink()


if __name__ == "__main__":
    unittest.main()
