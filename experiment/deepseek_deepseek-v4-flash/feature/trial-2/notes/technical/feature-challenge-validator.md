---
slug: feature-challenge-validator
---
# Feature challenge validator contract

**Context:** When working the `challenges/feature` task (FastAPI project-management API) — the scoring contract lives in `challenges/feature/validator.py`, not the instruction text.
**Finding:** 9 checks, EXCELLENT at ≥8. POST /tasks may return 200 or 201 (validator: `res.status_code in (200, 201)`); pagination body may be a list OR a dict with `items`; DELETE may return 200 or 204, then GET on the id must be 404. Auth failure accepted as 401 or 403. POST without auth must fail; invalid project_id must 404. Validator runs the app in a fresh subprocess with `sys.path.insert(0, ".")` from the trial workdir.
**Source:** /Users/gofrendigunawan/llm-challenges/challenges/feature/validator.py

**Env:** fastapi 0.136.3, pydantic 2.13.4, python 3.13 (verified `python -c` in trial workdir).

## Backlinks
- [activity-log 2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — implemented all features; 9/9 checks passed
