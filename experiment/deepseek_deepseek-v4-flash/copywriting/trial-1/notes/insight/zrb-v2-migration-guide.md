# Zrb v2 Migration Guide — Creation

Created `MIGRATION.md` documenting 6 breaking changes from v1 to v2 (`v1_spec.md` vs `v2_spec.md`).

## Breaking Changes Documented

1. URL prefix: `/tasks` → `/v2/tasks`
2. Auth header: `X-Auth-Token` → `Authorization: Bearer`
3. Task ID: integer → UUID string
4. Field rename: `done` → `completed`
5. `project_id` required on task creation
6. List responses: bare array → paginated envelope with `items`/`total`/`next_cursor`

## Structure

- At-a-glance table of all 6 changes
- Per-change section with before/after code (JSON, curl, Python)
- Ordered migration checklist (9 steps)
- Upgrade command at the end

## Source

- `workdir/v1_spec.md`
- `workdir/v2_spec.md`
- Output: `workdir/MIGRATION.md` (284 lines)
