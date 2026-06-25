---
slug: grep-fest
---
# Grep Fest Migration

**Context:** When migrating legacy authentication functions within the repository.
**Finding:** Successfully migrated 44 call sites of `legacy_auth(user_id)` to `new_auth(user_id, scope=...)`. Read-only actions map to `scope="read"`, while mutating/writing operations (where functions accept `payload: dict` or return `created`/`updated` status) map to `scope="write"`.
**Source:** app/auth.py

## Backlinks
- [projects/index.md](index.md) — project index listing
- [2026-06-25 Log](../activity-log/2026/2026-06/2026-06-25.md) — task completion log
