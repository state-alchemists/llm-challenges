# Auth Migration Insights

Insights learned from migrating deprecated `legacy_auth` function calls to the new `new_auth` with appropriate scope context.

## Summary
The migration scanned dozens of Python modules and determined the correct authentication scope based on the file and module context:
- `scope="write"` for write-like or mutating modules: `create`, `update`, `delete`, `sync`, `importer`, `cleanup`, `billing`, `notifier`, `mailer`, `tokens_repo`, `audit_repo`, `uploads`.
- `scope="read"` for read-only or generic modules.

## Key Decisions
- Standardized replacement of `legacy_auth(<user>)` using regex and clean automated script.
- Verified zero remaining `legacy_auth` calls except in `app/auth.py` itself.

## Backlinks
- [HUD](../index.md)
- [Technical Index](index.md)
- [Grep Fest Project](../projects/grep-fest.md)
- [2026-06-23 Log](../activity-log/2026/2026-06/2026-06-23.md)
