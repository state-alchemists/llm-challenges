---
slug: grep-fest-migration
---
# grep-fest: legacy_auth → new_auth migration

**Context:** Applies to the grep-fest challenge workdir (`experiment/deepseek_deepseek-v4-flash/grep-fest/trial-1/workdir`).
**Finding:** The `app/` package contained 44 `legacy_auth()` call sites across 37 auto-generated modules (each module = `handle_N` functions). Scope is signaled by the handler return payload: `{'created': True}` / `{'updated': True}` → `scope="write"`; `{'ok': True}` → `scope="read"`. The `legacy_auth` definition in `app/auth.py` must remain for external callers (it is the only permitted `legacy_auth(` occurrence).
**Source:** Grep over workdir: 44 call sites / 37 files; `app/auth.py:6` (definition kept); README.md (challenge description).

## Backlinks
- [activity-log 2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — performed the migration
