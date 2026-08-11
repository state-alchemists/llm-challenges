"""End-to-end contract tests: the refactored pipeline must produce the same
report information and database contents as the original script.

The original `pipeline.py` hardcodes paths, so it is run with no extra env and
its outputs are read from the working directory. The refactored script is run
with explicit env vars to prove configuration is honored.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
ORIGINAL_SCRIPT = SCRIPT_DIR / "pipeline.py"
REFACTORED_SCRIPT = SCRIPT_DIR / "pipeline_refactored.py"

REPORT_MARKERS = [
    "<h1>Error Summary</h1>",
    "<b>Database timeout</b>: 2 occurrences",
    "<h2>API Latency</h2>",
    "/users/profile",
    "250.0",
    "<h2>Active Sessions</h2>",
    "0 user(s) currently active",
]


def run_script(script: Path, cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run a pipeline script in `cwd` and return stdout; fail on errors."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def assert_report_and_db(db_path: Path, report_path: Path) -> None:
    """Assert the report and database carry the expected information."""
    report = report_path.read_text(encoding="utf-8")
    for marker in REPORT_MARKERS:
        assert marker in report

    connection = sqlite3.connect(str(db_path))
    try:
        error_rows = connection.execute(
            'SELECT message, "count" FROM errors ORDER BY message'
        ).fetchall()
        api_rows = connection.execute(
            'SELECT endpoint, avg_ms FROM api_metrics ORDER BY endpoint'
        ).fetchall()
    finally:
        connection.close()

    assert error_rows == [("Database timeout", 2)]
    assert len(api_rows) == 1
    assert api_rows[0][0] == "/users/profile"
    assert api_rows[0][1] == pytest.approx(250.0)


def test_original_pipeline_end_to_end(tmp_path: Path) -> None:
    """Baseline: capture what the current pipeline produces."""
    run_script(ORIGINAL_SCRIPT, tmp_path)
    assert (tmp_path / "server.log").is_file()  # sample log seeded
    assert_report_and_db(tmp_path / "metrics.db", tmp_path / "report.html")


def test_refactored_pipeline_end_to_end(tmp_path: Path) -> None:
    """The refactored pipeline must produce the same report and DB contents."""
    env = {
        "DB_PATH": str(tmp_path / "metrics.db"),
        "LOG_FILE": str(tmp_path / "server.log"),
        "REPORT_FILE": str(tmp_path / "report.html"),
    }
    run_script(REFACTORED_SCRIPT, tmp_path, env)
    assert_report_and_db(tmp_path / "metrics.db", tmp_path / "report.html")


def test_refactored_honors_env_paths_and_leaves_cwd_clean(tmp_path: Path) -> None:
    """Env vars must drive all output paths; nothing should land in the cwd."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (tmp_path / "db").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "out").mkdir()
    env = {
        "DB_PATH": str(tmp_path / "db" / "metrics.db"),
        "LOG_FILE": str(tmp_path / "logs" / "server.log"),
        "REPORT_FILE": str(tmp_path / "out" / "report.html"),
    }
    run_script(REFACTORED_SCRIPT, cwd, env)

    assert (tmp_path / "db" / "metrics.db").is_file()
    assert (tmp_path / "logs" / "server.log").is_file()
    assert (tmp_path / "out" / "report.html").is_file()
    assert not (cwd / "server.log").exists()
    assert not (cwd / "metrics.db").exists()
    assert not (cwd / "report.html").exists()
