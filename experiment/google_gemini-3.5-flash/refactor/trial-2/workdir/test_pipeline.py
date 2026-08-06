import os
import sqlite3
import subprocess
import pytest

def test_original_pipeline_execution():
    # Ensure starting clean
    for f in ["server.log", "metrics.db", "report.html"]:
        if os.path.exists(f):
            os.remove(f)

    # Run the original pipeline
    result = subprocess.run(["python3", "pipeline.py"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Connecting to localhost:5432 as admin" in result.stdout
    assert "Job finished at" in result.stdout

    # Verify log file was created
    assert os.path.exists("server.log")

    # Verify metrics.db was created
    assert os.path.exists("metrics.db")
    conn = sqlite3.connect("metrics.db")
    cursor = conn.cursor()

    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "errors" in tables
    assert "api_metrics" in tables

    # Verify errors table content
    cursor.execute("SELECT message, count FROM errors")
    errors = cursor.fetchall()
    assert len(errors) == 1
    assert errors[0] == ("Database timeout", 2)

    # Verify api_metrics table content
    cursor.execute("SELECT endpoint, avg_ms FROM api_metrics")
    metrics = cursor.fetchall()
    assert len(metrics) == 1
    assert metrics[0] == ("/users/profile", 250.0)

    conn.close()

    # Verify report.html content
    assert os.path.exists("report.html")
    with open("report.html", "r") as f:
        html = f.read()

    assert "<h1>Error Summary</h1>" in html
    assert "<li><b>Database timeout</b>: 2 occurrences</li>" in html
    assert "<h2>API Latency</h2>" in html
    assert "<tr><td>/users/profile</td><td>250.0</td></tr>" in html
    assert "<h2>Active Sessions</h2>" in html
    assert "<p>0 user(s) currently active</p>" in html

    # Clean up
    for f in ["server.log", "metrics.db", "report.html"]:
        if os.path.exists(f):
            os.remove(f)


def test_refactored_pipeline_execution():
    # Ensure starting clean
    for f in ["server.log", "metrics.db", "report.html"]:
        if os.path.exists(f):
            os.remove(f)

    # Run the refactored pipeline
    result = subprocess.run(["python3", "pipeline_refactored.py"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Connecting to localhost:5432 as admin" in result.stdout
    assert "Job finished at" in result.stdout

    # Verify log file was created
    assert os.path.exists("server.log")

    # Verify metrics.db was created
    assert os.path.exists("metrics.db")
    conn = sqlite3.connect("metrics.db")
    cursor = conn.cursor()

    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    assert "errors" in tables
    assert "api_metrics" in tables

    # Verify errors table content
    cursor.execute("SELECT message, count FROM errors")
    errors = cursor.fetchall()
    assert len(errors) == 1
    assert errors[0] == ("Database timeout", 2)

    # Verify api_metrics table content
    cursor.execute("SELECT endpoint, avg_ms FROM api_metrics")
    metrics = cursor.fetchall()
    assert len(metrics) == 1
    assert metrics[0] == ("/users/profile", 250.0)

    conn.close()

    # Verify report.html content
    assert os.path.exists("report.html")
    with open("report.html", "r") as f:
        html = f.read()

    assert "<h1>Error Summary</h1>" in html
    assert "<li><b>Database timeout</b>: 2 occurrences</li>" in html
    assert "<h2>API Latency</h2>" in html
    assert "<tr><td>/users/profile</td><td>250.0</td></tr>" in html
    assert "<h2>Active Sessions</h2>" in html
    assert "<p>0 user(s) currently active</p>" in html

    # Clean up
    for f in ["server.log", "metrics.db", "report.html"]:
        if os.path.exists(f):
            os.remove(f)

