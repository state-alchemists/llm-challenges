# Zrb CLI — v1 to v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples for each. Read it in full before upgrading — some changes require data migration (task IDs), not just code changes.

---

## Breaking Change 1: Authentication Header

The `X-Auth-Token` header has been removed. All requests must now use a Bearer token in the standard `Authorization` header. Requests still using `X-Auth-Token` receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

**Action:** Generate a v2 API token and update all client code to send the new header. The old token is not compatible.

---

## Breaking Change 2: Endpoint Prefix

All endpoints are now prefixed with `/v2/`. Requests to bare v1 paths return HTTP 404.

**Before (v1):**

```
GET  /tasks
GET  /tasks/{id}
POST /tasks
PUT  /tasks/{id}
DEL  /tasks/{id}
```

**After (v2):**

```
GET  /v2/tasks
GET  /v2/tasks/{id}
POST /v2/tasks
PUT  /v2/tasks/{id}
DEL  /v2/tasks/{id}
```

**Action:** Update base URLs and all hardcoded path references. If your client uses a base path configuration, change it from `/` to `/v2/`.

---

## Breaking Change 3: Task `id` Type (Integer → UUID)

Task IDs are now UUID strings instead of auto-incrementing integers. Existing integer IDs have been migrated to deterministic UUIDs. Any code that assumes `id` is an integer — type checks, math, DB references — must be updated.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Action:**
- Update type annotations: `int` → `string` / `UUID`.
- Remove any integer-arithmetic code that uses `id` (e.g., `id + 1`, `id % 2`).
- `GET /v2/tasks/{id}` — `{id}` is now a UUID string, not an integer path param.
- Stored references to old integer IDs must be mapped to their v2 UUID equivalents. Contact your account team for a migration mapping if needed.

---

## Breaking Change 4: Field Rename — `done` → `completed`

The `done` boolean field on task objects has been renamed to `completed`. The semantics are identical. Sending `done` in create/update requests elicits an HTTP 422; the response payload uses `completed`.

**Before (v1) — Request:**

```json
{
  "title": "New task",
  "done": true
}
```

**Before (v1) — Response:**

```json
{
  "id": 42,
  "title": "New task",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — Request:**

```json
{
  "title": "New task",
  "completed": true
}
```

**After (v2) — Response:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New task",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Action:** Rename every `done` reference — in request bodies, response parsers, and internal data models — to `completed`.

---

## Breaking Change 5: Task Creation Requires `project_id`

`POST /v2/tasks` now requires the `project_id` field in the request body. Omitting it returns HTTP 422. There is no default project — every task must belong to a project.

**Before (v1):**

```json
POST /tasks
{
  "title": "Write tests"
}
```

**After (v2):**

```json
POST /v2/tasks
{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

**Action:**
- Identify which project each task belongs to.
- Add `project_id` to every create-task call site.
- If your workflow creates tasks without a project concept, design a project hierarchy first (e.g., a single "General" catch-all project, or one project per user/team).

---

## Breaking Change 6: List Endpoints Return a Paginated Envelope

`GET /tasks` previously returned a bare JSON array. `GET /v2/tasks` returns a paginated envelope object, even when the result set fits in one page.

**Before (v1):**

```json
GET /tasks
→
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
GET /v2/tasks
→
{
  "items": [
    {"id": "a1b2…", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "d4e5…", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Action:**
- Change list-response parsers to read `.items` instead of treating the top-level value as the array.
- Use `.total` for display (e.g., "Showing 2 of 42 tasks").
- Implement cursor-based pagination: pass `?cursor=<next_cursor>` and `?limit=<n>` to fetch subsequent pages. When `next_cursor` is null or empty, all pages have been consumed.
- The default page size is 20 — specify `?limit=100` for larger pages (subject to server cap).

---

## Migration Checklist

Use this ordered list to track your migration. Most items can be parallelised, but data mapping (step 3) must finish before the cutover.

- [ ] **1. Generate v2 API tokens.** Create Bearer tokens for each environment. Store them securely — the old `X-Auth-Token` values are invalid after the cutover.
- [ ] **2. Update the base URL.** Change all endpoint paths from `/…` to `/v2/…` in configuration, environment variables, and hardcoded strings.
- [ ] **3. Map integer IDs to UUIDs.** Retrieve the migration mapping for existing tasks. Update any stored references (database columns, cache keys, audit logs, webhook payloads) to use the v2 UUIDs.
- [ ] **4. Rename `done` to `completed`.** Update every request builder, JSON deserialiser, and internal model that references the `done` field. Add CI lint rules to catch lingering `done` references.
- [ ] **5. Add `project_id` to task creation.** Identify the project for each creation path and inject the ID. Validate that `project_id` is always present before sending.
- [ ] **6. Update list-response parsing.** Replace bare-array deserialisation with envelope access: read `.items`, use `.total` for counts, implement cursor pagination.
- [ ] **7. Remove X-Auth-Token from all outgoing requests.** Verify with a staging test that no legacy header leaks through.
- [ ] **8. Run integration tests against v2 staging.** Cover every endpoint: auth rejection, create with/without `project_id`, list pagination, UUID-based GET, update with `completed`, delete.
- [ ] **9. Audit stored task references.** Search code, config files, and documentation for stale patterns: `X-Auth-Token`, `/tasks` (unprefixed), `"done"`, integer ID assumptions.

---

## Upgrade Command

Run the following to install Zrb CLI v2 (or the latest v2.x):

```bash
pip install --upgrade "zrb>=2.0.0"
```
