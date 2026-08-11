import os
import sqlite3
import subprocess
from pathlib import Path
import shutil

def run_pipeline_script(script_name: str, log_file: Path, db_file: Path, report_file: Path) -> None:
    # Prepare environment variables
    env = os.environ.copy()
    env["LOG_FILE"] = str(log_file)
    env["DB_PATH"] = str(db_file)
    
    # Run the script
    subprocess.run(["python3", script_name], env=env, check=True)

def test_equivalence():
    tmp_dir = Path("tmp_test")
    tmp_dir.mkdir(exist_ok=True)
    
    # Create test log content
    log_content = (
        "2024-01-01 12:00:00 INFO User 42 logged in\n"
        "2024-01-01 12:05:00 ERROR Database timeout\n"
        "2024-01-01 12:05:05 ERROR Database timeout\n"
        "2024-01-01 12:08:00 INFO API /users/profile took 250ms\n"
        "2024-01-01 12:09:00 WARN Memory usage at 87%\n"
        "2024-01-01 12:10:00 INFO User 42 logged out\n"
    )
    
    # Original pipeline files
    orig_log = tmp_dir / "server_orig.log"
    orig_db = tmp_dir / "metrics_orig.db"
    orig_report = tmp_dir / "report_orig.html"
    
    orig_log.write_text(log_content)
    if orig_db.exists():
        orig_db.unlink()
    if orig_report.exists():
        orig_report.unlink()
        
    # Refactored pipeline files
    ref_log = tmp_dir / "server_ref.log"
    ref_db = tmp_dir / "metrics_ref.db"
    ref_report = tmp_dir / "report_ref.html"
    
    ref_log.write_text(log_content)
    if ref_db.exists():
        ref_db.unlink()
    if ref_report.exists():
        ref_report.unlink()

    # We need pipeline.py to read our custom log file
    # But wait, original pipeline.py has LOG_FILE = "server.log" and DB_PATH = "metrics.db"
    # and it does not read them from environment variables because they are hardcoded constants!
    # So to test the original pipeline.py, we have to run it in a way that uses server.log and metrics.db
    # or temporarily replace server.log and metrics.db in the root, then copy them to the temp dir.
    
    # Let's save any existing files in root
    backup_log = Path("server.log")
    backup_db = Path("metrics.db")
    backup_report = Path("report.html")
    
    log_saved = backup_log.exists()
    db_saved = backup_db.exists()
    report_saved = backup_report.exists()
    
    if log_saved:
        shutil.move("server.log", "server.log.bak")
    if db_saved:
        shutil.move("metrics.db", "metrics.db.bak")
    if report_saved:
        shutil.move("report.html", "report.html.bak")
        
    try:
        # Run original pipeline
        backup_log.write_text(log_content)
        subprocess.run(["python3", "pipeline.py"], check=True)
        
        # Move outputs to orig
        shutil.move("metrics.db", orig_db)
        shutil.move("report.html", orig_report)
        backup_log.unlink()
        
        # Run refactored pipeline with env variables pointing to tmp_test
        # We will configure it to write to ref_db and ref_report, and read ref_log
        env = os.environ.copy()
        env["LOG_FILE"] = str(ref_log)
        env["DB_PATH"] = str(ref_db)
        # Note: refactored script might write report.html to a configured path,
        # or we can pass a REPORT_FILE env var, or it writes report.html to current dir.
        # Let's check how the refactored script handles HTML report path.
        # Let's support REPORT_FILE env var too!
        env["REPORT_FILE"] = str(ref_report)
        
        subprocess.run(["python3", "pipeline_refactored.py"], env=env, check=True)
        
        # If ref_report was written to report.html (if env not fully supported or fallback), move it
        if Path("report.html").exists():
            shutil.move("report.html", ref_report)
            
        # Compare HTML reports
        orig_html = orig_report.read_text()
        ref_html = ref_report.read_text()
        
        print("Original HTML:\n", orig_html)
        print("Refactored HTML:\n", ref_html)
        
        assert orig_html == ref_html, "HTML reports do not match!"
        
        # Compare DBs
        conn_orig = sqlite3.connect(orig_db)
        conn_ref = sqlite3.connect(ref_db)
        
        cursor_orig = conn_orig.cursor()
        cursor_ref = conn_ref.cursor()
        
        # Check errors table
        cursor_orig.execute("SELECT message, count FROM errors")
        orig_errors = cursor_orig.fetchall()
        cursor_ref.execute("SELECT message, count FROM errors")
        ref_errors = cursor_ref.fetchall()
        
        assert orig_errors == ref_errors, f"Errors table mismatch! Orig: {orig_errors}, Ref: {ref_errors}"
        
        # Check api_metrics table
        cursor_orig.execute("SELECT endpoint, avg_ms FROM api_metrics")
        orig_metrics = cursor_orig.fetchall()
        cursor_ref.execute("SELECT endpoint, avg_ms FROM api_metrics")
        ref_metrics = cursor_ref.fetchall()
        
        assert orig_metrics == ref_metrics, f"API metrics table mismatch! Orig: {orig_metrics}, Ref: {ref_metrics}"
        
        print("SUCCESS: Equivalence test passed!")
        
    finally:
        # Restore backups
        if orig_db.exists():
            orig_db.unlink()
        if orig_report.exists():
            orig_report.unlink()
        if ref_db.exists():
            ref_db.unlink()
        if ref_report.exists():
            ref_report.unlink()
        if ref_log.exists():
            ref_log.unlink()
        if (tmp_dir / "server_orig.log").exists():
            (tmp_dir / "server_orig.log").unlink()
        if tmp_dir.exists():
            tmp_dir.rmdir()
            
        if log_saved:
            shutil.move("server.log.bak", "server.log")
        if db_saved:
            shutil.move("metrics.db.bak", "metrics.db")
        if report_saved:
            shutil.move("report.html.bak", "report.html")

if __name__ == "__main__":
    test_equivalence()
