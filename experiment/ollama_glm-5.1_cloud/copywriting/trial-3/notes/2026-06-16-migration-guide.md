# Activity: Zrb v1→v2 Migration Guide

**Date:** 2026-06-16
**Task:** Write a developer migration guide for Zrb CLI v2 breaking changes
**Output:** `MIGRATION.md` in the trial-3 workdir

## Breaking changes covered
1. Endpoint path prefix `/v2/`
2. Auth header `X-Auth-Token` → `Authorization: Bearer`
3. Task `id` integer → UUID string
4. Task field `done` → `completed`
5. Task creation requires `project_id`
6. List responses: bare array → paginated envelope with cursor

## Notes
- Used Before-After-Bridge copywriting formula per core-writing skill
- Audience: experienced developers already on v1
- Each breaking change has before/after code examples in Python and HTTP
- Checklist maps 1:1 to the breaking changes
- Ends with `npm install zrb@2` upgrade command