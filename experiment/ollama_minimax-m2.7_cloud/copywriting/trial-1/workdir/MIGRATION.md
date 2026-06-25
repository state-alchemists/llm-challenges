# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change from v1 to v2 and how to update your integration.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints prefixed with `/v2/` | Update all URL paths |
| 2 | Auth header: `X-Auth-Token` → `Authorization: Bearer` | Update request headers |
| 3 | Task `id` changed from integer to UUID string | Update data types in your code |
| 4 | Task field `done` renamed to `completed` | Update field references |
| 5 | Task creation requires `project_id` | Add required field to create payloads |
| 6 | List endpoints return paginated envelope | Update response parsing |

---

## 1. Endpoint Prefix

All endpoints now live under `/v2/`.

**Before (v1):**
```http
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

## 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key
```

**After (v2):**
```http
Authorization: Bearer your_api_token
```

Requests using `X-Auth-Token` will receive `401 Unauthorized`.

---

## 3. Task ID Type

Task IDs are now UUIDs instead of integers.

**Before (v1) — integer ID:**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2) — UUID string:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update any code that stores, compares, or serializes task IDs to expect a UUID string.

---

## 4. Field Renamed: `done` → `completed`

The `done` boolean field is renamed to `completed`.

**Before (v1):**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-...", "title": "Ship v2", "completed": true }
```

Replace all references to `done` with `completed` in your objects and conditionals.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**
```json
{ "title": "New task" }
```

**After (v2):**
```json
{ "title": "New task", "project_id": "proj_abc123" }
```

You must provision a project first via your Zrb dashboard or Projects API before creating tasks.

---

## 6. List Response Envelope

List endpoints no longer return a bare array. They return a paginated envelope.

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
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To page through results, pass `?cursor=<next_cursor>` on the next request. Use `?limit=N` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all API base URLs to include `/v2/`
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID storage/data structures to handle UUID strings (not integers)
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to all task creation payloads (required field)
- [ ] Update list response parsing to unwrap the `items` array from the envelope
- [ ] Add pagination logic using `next_cursor` for list endpoints
- [ ] Update any integration tests for new response shapes

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```

Or, if you prefer pinning a specific version:

```bash
npm install @zrb/cli@2.0.0
```
