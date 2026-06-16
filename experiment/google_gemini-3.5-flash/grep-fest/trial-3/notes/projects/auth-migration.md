# Authentication Migration Project

Detailed facts and decisions on migrating deprecated `legacy_auth` usage to `new_auth`.

## Context & Details
- Old signature: `legacy_auth(user_id) -> bool`
- New signature: `new_auth(user_id, scope="read") -> bool`
- Both defined in `app/auth.py`.

## Completed Work
- Verified and classified all 44 call sites in the codebase across 37 files.
- Separated read vs write scope logically and accurately based on returns/state mutation in function bodies.
- Executed programmatic migration.
- Verified zero remaining internal call sites and import tidiness.
- Ensured all imports succeed.

## Backlinks
- [HUD](../index.md)
- [Projects Index](index.md)
- [Daily Log - 2026-06-16](../activity-log/2026/2026-06/2026-06-16.md)
