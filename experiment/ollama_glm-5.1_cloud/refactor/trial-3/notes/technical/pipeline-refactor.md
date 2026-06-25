---
slug: pipeline-refactor
---
# Pipeline Refactor Patterns

**Context:** Refactoring a monolithic Python log-processing script into Extract → Transform → Load.
**Finding:** Key patterns: (1) `Config` frozen dataclass from env vars replaces hardcoded constants; (2) three named regex patterns (`_LOG_LINE_RE`, `_USER_ACTION_RE`, `_API_CALL_RE`) replace fragile `str.split()` parsing; (3) `?` parameterized queries eliminate SQL injection from `%`-format string interpolation; (4) frozen dataclasses (`ErrorEvent`, `UserAction`, `ApiCall`) replace untyped dicts with single-char keys; (5) `html.escape()` prevents HTML injection in report generation; (6) `pathlib.Path` and context managers replace bare `open()`/`os.path`.
**Source:** pipeline_refactored.py

## Backlinks
- [2026-06-25 activity](../activity-log/2026/2026-06/2026-06-25.md) — refactoring performed this session