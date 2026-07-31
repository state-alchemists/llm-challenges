---
slug: refactor-challenge
---
# Refactor Challenge — Validator Criteria

**Context:** The `refactor` challenge in this repo (`challenges/refactor/validator.py`) grades pipeline refactors.
**Finding:** The validator (`RefactorValidator`) gives 10 checks, max score 8, EXCELLENT requires ≥7:
- env config: `os.getenv`/`os.environ` present
- no hardcoded credential: `password123` only allowed inside `os.getenv(...)` default
- SQL injection: `execute(` lines must not use `%[sdf]`, `+`, or f-strings
- ETL: content must contain "extract", "transform", and "load"/"report"
- ≥3 top-level `def` functions or ≥1 class
- `import re` or `re.` usage
- type hints (`->` or `: str|int|...`) and docstrings (`"""` or `'''`)
- script must exit 0 with env `LOG_FILE`/`DB_PATH`/`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS` set
- `report.html` must contain "error", "latency"/"api", "session", "database timeout", "/users/profile", "250"

Validator picks `pipeline_refactored.py` before `pipeline.py`, then any other `.py`. It runs the script with a 6-line fixture; it overwrites `server.log` itself.
**Source:** challenges/refactor/validator.py:1-320

## Backlinks
- [activity 2026-07-31](activity-log/2026/2026-07/2026-07-31.md) — pipeline refactor passed all checks
