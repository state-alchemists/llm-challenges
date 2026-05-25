---
slug: v2-migration-guide
---
# Zrb v2 API Migration Guide

**Context:** Developers migrating from Zrb CLI v1 to v2.
**Finding:** Six breaking changes between v1 and v2: endpoint prefix (`/v2/`), auth header (`Authorization: Bearer`), task ID type (integer → UUID), field rename (`done` → `completed`), new required field (`project_id`), and list response format (bare array → paginated envelope with `items`/`total`/`next_cursor`).
**Source:** `v1_spec.md`, `v2_spec.md`
