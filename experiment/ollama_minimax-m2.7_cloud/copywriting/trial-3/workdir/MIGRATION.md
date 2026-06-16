# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and how to update your integration.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

**What changed:** Every endpoint path now includes the version prefix. Requests to v1 paths will return `404`.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication header changed

**What changed:** The `X-Auth-Token` header is no longer accepted. v2 uses Bearer token authentication. Requests with the old header will receive `401 Unauthorized`.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

---

### 3. Task `id` is now a UUID string, not an integer

**What changed:** Task IDs changed from auto-incrementing integers to UUID strings. Any code that treats `id` as a number will break.

**Before (v1):**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

If you store task IDs in a database, update the column type from `INTEGER` to `VARCHAR(36)` or your database's UUID type.

---

### 4. Task field `done` renamed to `completed`

**What changed:** The `done` boolean is now `completed`. Update all field references in your code.

**Before (v1):**
```json
{ "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "title": "Ship v2", "completed": true }
```

---

### 5. Task creation now requires `project_id`

**What changed:** Creating a task without a `project_id` returns `422 Unprocessable Entity`. The `project_id` field is mandatory.

**Before (v1):**
```json
{ "title": "New task" }
```

**After (v2):**
```json
{ "title": "New task", "project_id": "proj_abc123" }
```

You must provision a project first via `POST /v2/projects` (if available) or use an existing `project_id` from your workspace.

---

### 6. List endpoints return a paginated envelope, not a bare array

**What changed:** `GET /v2/tasks` no longer returns a raw array. It returns a paginated envelope with `items`, `total`, and `next_cursor`. Update your parsing logic.

**Before (v1):**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false },
    { "id": "...", "title": "Ship v1", "completed": true }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, pass `?cursor=<next_cursor>` on the next request.

---

## Migration Checklist

Run through each step in order:

- [ ] **Update all endpoint paths** — add `/v2/` prefix to every URL
- [ ] **Update authentication header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change `id` from integer to string; update any database columns storing task IDs
- [ ] **Replace `done` with `completed`** — rename the field in all request/response handling code
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` body must include a valid `project_id`
- [ ] **Update list response parsing** — extract `items` from the envelope instead of using the response directly
- [ ] **Implement pagination** — use `next_cursor` to page through results when `next_cursor` is present
- [ ] **Update any tests** — replace hardcoded v1 payloads and assertions with v2 equivalents
- [ ] **Verify 401 responses** — confirm that requests without Bearer token are rejected with `401`
- [ ] **Test end-to-end** — create a task, mark it complete, list tasks, delete a task

---

## Upgrade Command

```bash
pip install --upgrade zrb
```

After upgrading, confirm your version:

```bash
zrb --version
```

---

If you hit a breaking change not covered here, check the full [v2 specification](./v2_spec.md) or open an issue on the repository.