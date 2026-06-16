# Zaruba HUD

Heads-Up Display for Zaruba's grep-fest challenge.

## Active Constraints & Goals
- Migrate deprecated `legacy_auth(user_id)` to `new_auth(user_id, scope=...)`.
- Definition of `legacy_auth` must remain in `app/auth.py` but must have 0 call sites.
- Tidied imports everywhere.
- Project must pass `import app` checks.

## Key Projects & Context
- [Authentication Migration Project](projects/auth-migration.md)

## Recent Insights
- [Scope Partition Insight](technical/scope-partition.md)

## Navigation
- [Projects Index](projects/index.md)
- [Technical Notes Index](technical/index.md)
- [Activity Log Index](activity-log/index.md)
