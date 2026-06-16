# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, improved pagination, and stricter authentication. Several v1 conventions are breaking changes — this guide covers every one with before/after examples.

---

## Breaking Changes

### 1. Endpoint Prefix Changed to `/v2/`

All endpoints are now under `/v2/`. Requests to v1 paths receive `404`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```http
GET /tasks HTTP/1.1
Host: api.zrb.io
X-Auth-Token: your_api_key
```

**After:**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
Authorization: Bearer your_api_token
```

---

### 2. Authentication Header Changed

`X-Auth-Token` is no longer accepted. v2 uses a Bearer token in the standard `Authorization` header. Requests with `X-Auth-Token` will receive `401 Unauthorized`.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |

**Before:**
```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key
```

**After:**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token
```

---

### 3. Task `id` Is Now a UUID String

Task IDs changed from auto-incremented integers to UUID strings. Any code that parses or stores `id` as an integer will break.

| v1 | v2 |
|---|---|
| `"id": 42` (integer) | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` (UUID string) |

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Field `done` Renamed to `completed`

The boolean completion flag is now named `completed`. Code referencing `.done` will silently read `undefined`.

| v1 | v2 |
|---|---|
| `"done": true` | `"completed": true` |

**Before (update task):**
```json
{
  "done": true
}
```

**After (update task):**
```json
{
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`. This is a new mandatory association — you must create or select a project first.

| v1 | v2 |
|---|---|
| `{ "title": "New task" }` | `{ "title": "New task", "project_id": "proj_abc123" }` |

**Before (create task):**
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (create task):**
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Is Now Paginated

List endpoints return a wrapped envelope instead of a bare array. Access tasks via `response.items`. Pagination uses a cursor string — fetch the next page by passing `?cursor=<next_cursor>`.

| v1 | v2 |
|---|---|
| `[{"id": 1, ...}, {"id": 2, ...}]` | `{ "items": [...], "total": 42, "next_cursor": "cursor_xyz" }` |

**Before (list tasks):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (list tasks):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

**Fetching the next page:**
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20 HTTP/1.1
Authorization: Bearer your_api_token
```

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Update task `id` handling — change integer parsing to UUID string handling
- [ ] Rename all occurrences of `.done` / `"done"` to `.completed` / `"completed"`
- [ ] For task creation: add required `project_id` field; create a project if none exists
- [ ] Update list response handling: access tasks via `response.items`, read `response.total` for count, use `response.next_cursor` for pagination
- [ ] Update any code that stores or indexes task IDs — integer-to-UUID is not a cast, it is a new ID format
- [ ] Run integration tests against the v2 endpoints before deploying

---

## Upgrade Command

```bash
# Install the v2 CLI
pip install --upgrade zrb==2.0.0
```