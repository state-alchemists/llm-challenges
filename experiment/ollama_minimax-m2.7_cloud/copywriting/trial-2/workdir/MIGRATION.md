# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between v1 and v2 and how to update your code.

## Breaking Changes at a Glance

| # | Change | Field/Endpoint |
|---|--------|----------------|
| 1 | API versioning prefix | All endpoints now under `/v2/` |
| 2 | Authentication header | `X-Auth-Token` → `Authorization: Bearer` |
| 3 | Task ID type | integer → UUID string |
| 4 | Task status field | `done` → `completed` |
| 5 | Task creation requirement | `project_id` is now required |
| 6 | List response format | bare array → paginated envelope |

---

## 1. API Versioning Prefix

All endpoints are now versioned under `/v2/`.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

## 2. Authentication Header

The authentication header has changed from a custom header to a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests using `X-Auth-Token` will receive HTTP 401.

---

## 3. Task ID Type

Task IDs are now UUID strings instead of integers.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

Update all code that stores, parses, or references task IDs to handle string values. Database columns or local caches storing integer IDs must be migrated.

---

## 4. Task Status Field Renamed

The `done` boolean field has been renamed to `completed`.

**Before (v1):**
```json
{
  "title": "Ship v1",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Ship v2",
  "completed": true
}
```

Update all task update payloads and response handling.

---

## 5. Project ID Required on Task Creation

Creating a task now requires a `project_id`. Tasks are no longer created in a global namespace.

**Before (v1):**
```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2):**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` returns HTTP 422. All existing integrations must specify a project when creating tasks.

---

## 6. List Response Envelope

List endpoints no longer return a bare array. They now return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```json
GET /v2/tasks
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To paginate, pass `?cursor=<next_cursor>` on the next request. Use `?limit=N` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs to use `/v2/` prefix
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Update task ID handling — change integer fields to strings
- [ ] Rename all `done` fields to `completed` in request/response code
- [ ] Add required `project_id` to all task creation calls
- [ ] Update list response parsing to unwrap the envelope (`items`, `total`, `next_cursor`)
- [ ] Implement cursor-based pagination for list operations
- [ ] Update any database columns or caches storing task IDs from integer to string/UUID
- [ ] Update integration tests for new response shapes and field names

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```
