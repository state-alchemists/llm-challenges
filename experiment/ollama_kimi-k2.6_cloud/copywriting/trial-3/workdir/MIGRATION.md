# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change in Zrb CLI v2 and shows you exactly how to update your code.

---

## 1. API Version Prefix Required

All endpoints must now include the `/v2/` prefix. Requests to unversioned paths will fail.

### Before (v1)
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. You must switch to a Bearer token in the `Authorization` header.

### Before (v1)
```
X-Auth-Token: <your_api_key>
```

### After (v2)
```
Authorization: Bearer <your_api_token>
```

> **Impact:** Requests sent with `X-Auth-Token` will receive HTTP 401.

---

## 3. Task `id` Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any client-side code that assumes `id` is numeric or performs integer comparisons.

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

> **Impact:** Database schemas, URL routing, and client models that store `id` as an `INTEGER` type must be migrated to `STRING`/`VARCHAR`.

---

## 4. Task Field `done` Renamed to `completed`

The boolean field indicating task status has been renamed. Update all JSON payloads and response parsing.

### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

> **Impact:** Any code referencing `task.done` must be updated to `task.completed`.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` in the request body. Omitting it returns HTTP 422.

### Before (v1)
```json
POST /tasks
{
  "title": "New task title"
}
```

### After (v2)
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

> **Impact:** If your application creates tasks without a project context, you must assign a default project or update the creation flow to collect a `project_id`.

---

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update list parsing and implement cursor-based pagination.

### Before (v1)
```json
GET /tasks

[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```json
GET /v2/tasks

{
  "items": [
    {"id": "a1b2c3d4...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "b2c3d4e5...", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:
```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

> **Impact:** All list consumers must be updated to read `response.items` instead of the top-level array.

---

## Migration Checklist

Use this checklist to verify your upgrade is complete:

- [ ] Update base API URL to include `/v2/` prefix on all endpoints
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change all task `id` fields from integer to UUID/string type
- [ ] Rename all references from `done` to `completed` in request bodies and response parsing
- [ ] Add `project_id` to all task creation payloads
- [ ] Update list-task consumers to read from `items` array inside paginated envelope
- [ ] Implement cursor-based pagination using `next_cursor` and `?cursor=` query param
- [ ] Update database schemas and client models that store task IDs as integers
- [ ] Run integration tests against the v2 endpoints

---

## Upgrade Command

```bash
pip install --upgrade zrb
```

After upgrading, verify the installed version:

```bash
zrb --version
```
