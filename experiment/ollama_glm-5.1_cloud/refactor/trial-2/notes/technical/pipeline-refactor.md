# Pipeline Refactor — Challenge Patterns

## Context
Refactoring the `pipeline.py` log-processing script for the LLM challenges benchmark.

## Key Findings

- **Validator checks**: 8 checks, 3 critical (hardcoded credentials, SQL injection, script+report correctness). Critical failures cap score at 0.4.
- **Credential safety**: `password123` is only allowed inside `os.getenv()`/`os.environ.get()` as a default — bare assignments, f-strings, or dict literals are flagged as leaks.
- **SQL injection patterns detected**: `%s`/`%d`/`%f`, `+` concatenation, or f-strings inside `execute()` calls.
- **ETL naming**: function names must contain "extract", "transform", and "load" or "report" (case-insensitive substring match).
- **Report content**: must contain "database timeout", "/users/profile", and "250" in the HTML, plus sections with "error", "latency"/"api", and "session".
- **Active sessions**: user 42 logs in then logs out in the fixture, so the active session count is 0.

## Backlinks
- [2026-06-15 log](../activity-log/2026/2026-06/2026-06-15.md) — refactor completed this day