# Grep Fest Project

Details about the Grep Fest migration challenge.

## Scope
- Deprecate internal call sites of `legacy_auth(user_id)`.
- Use `new_auth(user_id, scope=...)`.
- Target: `scope="write"` for write-like actions and `scope="read"` for others.

## Progress
- Completed migrating all 44 call sites in the repository.
- Verified cleanly importing the package post-migration.

## Backlinks
- [HUD](../index.md)
- [Projects Index](index.md)
- [Auth Migration Insights](../technical/auth-migration.md)
- [2026-06-23 Log](../activity-log/2026/2026-06/2026-06-23.md)
