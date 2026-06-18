---
slug: zrb-v2-migration
---
# Zrb v2 Migration Guide Created

**Context:** Creating a comprehensive developer migration guide to support transitioning from Zrb CLI v1 to v2.
**Finding:** A successful migration guide requires clear descriptions and before/after code blocks for 6 key breaking changes: prefix updates (`/v2/`), Bearer Token authentication (`Authorization: Bearer`), Task ID UUID migration, task boolean renaming (`done` to `completed`), required `project_id` upon creation, and paginated response envelopes.
**Source:** v1_spec.md, v2_spec.md

## Backlinks
- [Projects Index](index.md) — project listing
- [2026-06-19 log](../activity-log/2026/2026-06/2026-06-19.md) — creation of the migration guide
