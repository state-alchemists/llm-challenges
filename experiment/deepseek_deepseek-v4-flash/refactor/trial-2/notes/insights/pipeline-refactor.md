# pipeline.py → pipeline_refactored.py

Refactored the monolithic `pipeline.py` into an ETL-structured `pipeline_refactored.py` with 7 focused functions.

## Changes

| Issue | Before | After |
|-------|--------|-------|
| Config | Hardcoded `DB_PATH`, `LOG_FILE`, credentials | `load_config()` via `os.getenv()` with sensible defaults |
| SQL injection | `"INSERT ... VALUES ('%s', '%s', %d)" % (val1, val2, val3)` | Parameterized `"INSERT ... VALUES (?, ?, ?)"` with tuples |
| Structure | One ~100-line `proc_data()` function | 7 functions: `extract_logs`, `transform_errors`, `transform_api_latency`, `transform_sessions`, `load_database`, `load_report`, `main` |
| Log parsing | `line.split(" ")` + index slicing | `re.compile()` with named groups (`_LOG_PATTERN`, `_USER_PATTERN`, `_API_PATTERN`) |
| Types/docs | None | All functions have type hints and docstrings |

## Output preservation

- `report.html` still produces: error summary (grouped by message), API latency table (endpoint + avg), active session count
- SQLite DB still writes `errors` and `api_metrics` tables
- Fixture-creation fallback preserved if log file doesn't exist
