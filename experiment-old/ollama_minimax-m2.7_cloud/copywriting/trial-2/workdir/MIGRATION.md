# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb v1 to v2. Each section shows the exact before/after to make migration straightforward.

## Breaking Changes Summary

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/tasks` → `/v2/tasks` | Update all route definitions |
| 2 | Auth header `X-Auth-Token` → `Authorization: Bearer` | Update request construction |
| 3 | Task `id` is now a UUID string, not integer | Update ID handling and storage |
| 4 | Field `done` renamed to `completed` | Update field references |
| 5 | Creating a task now requires `project_id` | Add project association |
| 6 | List endpoints return a paginated envelope, not a bare array | Update response parsing |

---

## 1. Endpoint Prefix

All endpoints now carry the `/v2/` prefix.

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

## 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests with `X-Auth-Token` will now receive `401 Unauthorized`.

---

## 3. Task ID Type: Integer → UUID

Task IDs are no longer integers. They are now UUID strings.

**Before (v1) — integer ID:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "..."}
```

**After (v2) — UUID string:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
```

Update any code that:
- Stores task IDs as integers
- Constructs URLs with integer IDs
- Parses IDs as integers in typed languages

---

## 4. Field Renamed: `done` → `completed`

The task completion field has been renamed.

**Before (v1):**
```json
{"done": true}
```

**After (v2):**
```json
{"completed": true}
```

Update field references in:
- Update request bodies
- Conditional logic checking task state
- Serialization/deserialization logic

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field.

**Before (v1) — create task:**
```json
{"title": "New task title"}
```

**After (v2) — create task:**
```json
{"title": "New task title", "project_id": "proj_abc123"}
```

Omitting `project_id` returns `422 Unprocessable Entity`. If you don't yet have projects, you must create one first:

```bash
POST /v2/projects
{"name": "My Project"}
```

Then use the returned `proj_xxx` ID when creating tasks.

---

## 6. List Response: Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope.

**Before (v1) — list response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — paginated envelope:**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the `next_cursor` value:
```http
GET /v2/tasks?cursor=cursor_xyz
```

---

## Migration Checklist

Work through these steps in order:

- [ ] **Update endpoint URLs** — prefix all paths with `/v2/`
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change ID storage from integer to string/UUID type
- [ ] **Update field name** — replace all references to `done` with `completed`
- [ ] **Add project association** — determine which project new tasks belong to; create a project if none exists
- [ ] **Update list parsing** — change code that reads list responses to access `.items` array instead of the root array
- [ ] **Add pagination support** — if you consume all tasks, implement cursor-based pagination using `next_cursor`
- [ ] **Handle new error codes** — `422` on create without `project_id`, `401` on bad auth

---

## Upgrade Command

```bash
npm install zrb@latest
# or
pip install zrb==2.0.0
```

After upgrading, test your integration against the v2 endpoints before deploying to production.