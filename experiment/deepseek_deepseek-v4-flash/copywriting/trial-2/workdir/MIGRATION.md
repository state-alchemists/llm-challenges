# Zrb Task API — v1 to v2 Migration Guide

Zrb v2 introduces projects, pagination, and a stricter authentication model. The v1 API will continue to be available for a deprecation window, but new features ship on v2 only. This guide covers every breaking change and the steps required to migrate.

---

## Breaking Changes Overview

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/v2/` added | All request URLs change |
| 2 | Auth header changed to Bearer token | Every request needs a new header |
| 3 | Task `id` changed from integer to UUID | ID-based lookups and references break |
| 4 | Field `done` renamed to `completed` | Reads and writes of task status break |
| 5 | `project_id` required on task creation | Create calls without it now fail (422) |
| 6 | List endpoints return paginated envelope | Response structure changes; bare array gone |

---

## 1. Endpoint Prefix

All endpoints are now served under `/v2/`. The v1 paths (`/tasks`, `/tasks/{id}`) return HTTP 404.

**Before (v1):**

```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The `X-Auth-Token` header has been replaced with a standard Bearer token. Requests using the old header receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: sk-abc123
```

**After (v2):**

```http
Authorization: Bearer sk-abc123
```

Update all clients, SDK wrappers, and curl commands.

---

## 3. Task ID Type — Integer to UUID

Task identifiers are now UUID v4 strings. Integer IDs no longer exist in v2. Any system that stores, compares, or displays task IDs must handle the new string format.

**Before (v1 response):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 response):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Check for code that assumes `id` is numeric (e.g. `id > 100` range checks, integer arithmetic, type comparisons) and update accordingly.

---

## 4. Field Rename — `done` → `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. Both the request body (when creating or updating tasks) and the response body are affected.

**Before (v1) — response:**

```json
{
  "id": 1,
  "title": "Ship v1",
  "done": true,
  "created_at": "..."
}
```

**After (v2) — response:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "..."
}
```

**Before (v1) — update request:**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — update request:**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Search your codebase for `"done"`, `.done`, `['done']`, or similar access patterns on task objects and rename them to `completed`.

---

## 5. Required `project_id` on Task Creation

Every task must now belong to a project. The `project_id` field is required when creating a task. Omitting it returns HTTP 422 with a validation error.

**Before (v1) — create request:**

```json
{
  "title": "New task title"
}
```

**After (v2) — create request:**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

If you do not yet have a project, create one first via the projects endpoint, then use its `project_id` when creating tasks.

---

## 6. List Response — Paginated Envelope

List endpoints (e.g. `GET /v2/tasks`) no longer return a bare array. They return a paginated envelope object. The old response parsed as an array will break immediately.

**Before (v1) — list response:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — list response:**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Access the task array via the `items` key instead of using the response directly. Use the `next_cursor` value to paginate:

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

Optional query parameters:
- `cursor` — pagination cursor from the previous response
- `limit` — max results per page (default: 20)

---

## Migration Checklist

Use this checklist to track your migration progress. Each item maps to one of the breaking changes above.

- [ ] **Update all endpoint URLs** — prepend `/v2/` to every API path.
- [ ] **Replace auth header** — change `X-Auth-Token` to `Authorization: Bearer` on every request.
- [ ] **Update task ID handling** — change storage, comparison, and display logic from integer to UUID string.
- [ ] **Rename `done` to `completed`** — update all read and write paths that reference the task completion field.
- [ ] **Add `project_id` to task creation** — include a valid project ID in every `POST /v2/tasks` request.
- [ ] **Adapt list response parsing** — access items via `response.items` (or equivalent) and add cursor-based pagination where full lists are needed.
- [ ] **Update any SDKs or client libraries** — bump or regenerate if pointing at hardcoded v1 paths or schemas.
- [ ] **Test against a staging environment** — run your test suite against the v2 API before deploying to production.

---

## Upgrade

```bash
pip install --upgrade zrb
```

After upgrading, update your API base URL from `https://api.zrb.io` to `https://api.zrb.io/v2` (or the appropriate v2 base URL for your deployment) and apply the checklist above.
