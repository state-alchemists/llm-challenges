---
slug: failing-tests-trial2-bugs
---
# failing-tests trial-2: the 10 planted bugs

**Context:** `failing-tests` challenge workdir had 10 failing tests across 3 modules; fix only `src/`, never `tests/`.
**Finding:** Each module held independent, classic planted bugs:
- `src/auth.py` — `has_permission` used case-sensitive `in` (fix: compare `role.lower()`); `is_admin_or_owner` used `and` instead of `or` (admin OR owner).
- `src/inventory.py` — mutable default `{}` shared between instances (fix: `None` default + copy); `add` overwrote instead of accumulating; `reserve` used `qty >= available` (off-by-one; should be `>`); `release` never guarded against releasing more than reserved (needs `ValueError`).
- `src/text_utils.py` — `slugify` never lowercased and `replace("--","-")` collapsed only one run (fix: lowercase + `re.sub(r"-+", "-")`); `truncate` appended suffix without trimming (fix: `text[:max_len - len(suffix)] + suffix`).
**Source:** verified by `pytest -q` → 15 passed, 0 failed (2026-07-31 session).

## Backlinks
- [activity log 2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — session entry
