# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between Zrb CLI v1 and v2, with step-by-step instructions to update your integration.

---

## Overview

v2 introduces three new capabilities — projects, cursor-based pagination, and Bearer token auth — alongside several field and endpoint changes that require code updates.

**Timeline:** v1 endpoints at `/tasks/*` are no longer served. All requests must target `/v2/tasks/*`.

---

## Breaking Changes

### 1. Endpoint URL Prefix

All endpoints now carry a `/v2/` prefix. Requests to v1 paths return `404`.

| Operation | v1 | v2 |
|-----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header

The `X-Auth-Token` header is no longer accepted. v2 uses the standard `Authorization: Bearer` scheme.

**Before:**
```http
X-Auth-Token: your_api_key_here
```

**After:**
```http
Authorization: Bearer your_api_token_here
```

Migrating? Replace the header name and wrap the token in `Bearer <token>`.

---

### 3. Task ID Type: Integer → UUID

Task IDs changed from auto-incrementing integers to UUID strings.

v1 example: `"id": 42`  
v2 example: `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

**Impact:** Any code that stores or references task IDs as integers must be updated to handle UUID strings. Database columns, foreign keys, and cache keys using integer IDs need migration.

---

### 4. Task Field Renamed: `done` → `completed`

The `done` boolean field is renamed to `completed`.

**Before:**
```json
{
  "id": 1,
  "title": "Write tests",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Update all JSON serialization/deserialization logic, database columns, and API request bodies.

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns HTTP 422.

**Before:**
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After:**
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

If you don't already use projects, create one first via `zb project create` or the Projects API, then pass its ID when creating tasks.

---

### 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After:**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the subsequent request. The `limit` query parameter (default 20) controls page size.

---

## Migration Checklist

Run through each step in order. Mark each done as you complete it.

- [ ] **Update base URL.** Prefix all task endpoints with `/v2/`.
- [ ] **Update auth header.** Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate task ID storage.** Change any database columns, cache keys, or variables holding task IDs from integer to UUID (string) type.
- [ ] **Rename `done` to `completed`.** Update JSON serialization, API request bodies, and any conditional logic (`task.done` → `task.completed`).
- [ ] **Add `project_id` to task creation.** If creating tasks, fetch or create a project and include `project_id` in the request body.
- [ ] **Update list response handling.** Change code that iterates a bare array to unwrap the `items` array from the envelope.
- [ ] **Implement cursor pagination.** If you fetch all pages, loop on `next_cursor` until it is `null`.
- [ ] **Update integration tests.** Use UUID IDs, the new field name, the new envelope structure, and Bearer auth.
- [ ] **Deploy and verify.** Confirm list, create, get, update, and delete all work against the live v2 API.

---

## Upgrade Command

```bash
zb upgrade
```
