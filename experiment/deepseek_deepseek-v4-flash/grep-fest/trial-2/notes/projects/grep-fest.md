---
slug: grep-fest
---
# Grep-Fest Challenge: legacy_auth → new_auth migration

**Context:** `challenges/grep-fest` — large-repo migration benchmark; applies when a deprecated function must be migrated repo-wide with per-site scope selection.
**Finding:** 44 call sites across 37 files under `app/`. Scope is determinable from the surrounding function: handlers returning `{'created'/'updated': True}` or named `*_create`/`*_update`/`*_delete` (importer, users_create, notifier, audit_repo, users_update, mailer, billing, tokens_repo, users_delete, cleanup, comments_create, uploads_create, sync, posts_create, posts_update) → `scope="write"` (16 sites); handlers returning `{'ok': True}` (list/get/search/repo reads, utils, most workers) → `scope="read"` (28 sites). The `legacy_auth` definition in `app/auth.py` must remain for external callers.
**Source:** workdir/app (grep `legacy_auth` → 83 matches = 37 imports + 44 calls + 2 def/docstring; after migration → 2 matches, both in app/auth.py)

## Backlinks
