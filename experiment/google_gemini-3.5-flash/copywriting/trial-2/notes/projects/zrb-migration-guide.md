# Zrb Migration Guide Project

## Status
Completed. `MIGRATION.md` has been successfully generated.

## Facts and API Differences
- All v2 endpoints are now prefixed with `/v2/` instead of `/`.
- Authentication changed from `X-Auth-Token` to standard Bearer token `Authorization: Bearer <your_api_token>`.
- Task `id` is a UUID string instead of an integer.
- The `done` field is renamed to `completed`.
- Task creation now requires `project_id`, which was not present in v1.
- All listing endpoints return a paginated envelope structure (`{items, total, next_cursor}`) rather than a bare array.
- CLI upgrade command is `pip install --upgrade zrb`.

## Backlinks
- [Projects Index](index.md)
- [Activity Log Day](../../activity-log/2026/2026-06/2026-06-25.md)
