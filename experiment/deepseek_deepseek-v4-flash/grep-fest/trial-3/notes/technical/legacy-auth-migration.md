---
slug: legacy-auth-migration
---
# legacy_auth → new_auth migration

**Context:** grep-fest challenge — 83 call sites of `legacy_auth` across 37 files in app/{api,db,services,utils,workers}

**Finding:** Scope assignment per module was determined by function signature and return value:
- `scope="write"`: functions accepting `payload: dict` and returning `{'created': True, ...}` or `{'updated': True, ...}`, or modules named `create`/`update`/`delete`/`upload`
- `scope="read"`: functions accepting only `user_id` and returning `{'ok': True}`, or modules named `get`/`list`/`search`/`export`

**Strategy:** Bulk sed for efficiency — one pass for imports, two passes for call sites (write-scope vs read-scope), since the argument variable name varied (`user_id`, `user_id_1`, `user_id_2`).

**Result:** Zero call sites remain outside the `legacy_auth` definition in `app/auth.py:6`, which is preserved for external consumers. `python -c "import app"` passes.
