---
slug: refactor-challenge
---
# Refactor Challenge — Validator Acceptance Criteria

**Context:** Applies when refactoring `challenges/refactor/workdir/pipeline.py` (any trial).
**Finding:** The validator (`challenges/refactor/validator.py`) scores 8 checks; critical failures are: hardcoded `password123` anywhere except inside an `os.getenv(...)`/`os.environ.get(...)` fallback, non-parameterized `execute()` (interpolation `%s`/`%d`/`%f`, `+` concat, or f-string), non-zero script exit, or report missing data. It runs the script with env vars set — `LOG_FILE`, `DB_PATH`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS` — so env must win over defaults. `report.html` must contain "error", "latency"/"api", "session", "database timeout", "/users/profile", "250". File name may be `pipeline_refactored.py` or `pipeline.py`. Score ≥7/8 = EXCELLENT; `os.getenv("DB_PASS", "password123")` fallback is explicitly allowed, but an empty default also passes.
**Source:** `challenges/refactor/validator.py:117-320`; validated run 2026-07-31 → EXCELLENT 1.0.

## Backlinks
- [2026-07-31 activity](../activity-log/2026/2026-07/2026-07-31.md) — refactor completed and validated
