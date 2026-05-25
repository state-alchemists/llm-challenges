---
slug: pipeline-refactor
---
# pipeline.py → pipeline_refactored.py

**Context:** Original `pipeline.py` had hardcoded config, SQL injection via `%` formatting, one monolithic function, fragile `split(" ")` parsing, no type hints or docs.
**Finding:** Refactored to `pipeline_refactored.py` with:
- `Config` frozen dataclass loaded from env vars (`PIPELINE_DB_PATH`, `PIPELINE_LOG_FILE`, etc.)
- `parse_log_line()` using four compiled `re.compile` patterns (ERROR, WARN, USER, API)
- ETL decomposition: `read_log_file()` → `count_errors()`, `compute_api_latency()`, `track_active_sessions()` → `init_database()`, `insert_error_summary()`, `insert_api_metrics()`, `generate_html_report()`, `write_report()`
- Parameterized SQL (`VALUES (?, ?, ?)`) eliminating injection
- All functions ≤30 lines, type hints on every signature, docstrings on every public function
- Same `report.html` output format verified
**Source:** `pipeline_refactored.py:1-250`
