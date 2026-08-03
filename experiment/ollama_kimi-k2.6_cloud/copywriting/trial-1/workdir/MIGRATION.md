# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change in Zrb CLI v2 and how to update your code.

---

## 1. API endpoints are now version-prefixed

All endpoints now live under `/v2/`. Requests to the old unprefixed paths will return HTTP 404.

### Before (v1)
```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication header changed

The `X-Auth-Token` header is removed. v2 uses a standard Bearer token in the `Authorization` header. Requests sent with `X-Auth-Token` will receive HTTP 401.

### Before (v1)
```http
X-Auth-Token: <your_api_key>
```

### After (v2)
```http
Authorization: Bearer <your_api_token>
```

---

## 3. Task IDs changed from integer to UUID

Task `id` fields are now UUID strings instead of integers. If your code assumes `id` is an integer or uses integer operations (sorting, comparison, etc.), update it to treat IDs as opaque strings.

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

---

## 4. `done` field renamed to `completed`

The task status field is now called `completed`. Sending `done` in a request body will be ignored (or rejected where the field is validated).

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

---

## 5. Task creation now requires `project_id`

Creating a task without a `project_id` now returns HTTP 422.

### Before (v1)
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2)
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`.

### Before (v1)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:
```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

---

## Migration Checklist

Use this checklist to migrate each integration:

- [ ] Update the base URL or route prefix to `/v2/`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task ID handling from integer to string (UUID)
- [ ] Rename `done` to `completed` in all request/response handling code
- [ ] Add `project_id` to every task creation request
- [ ] Update list-tasks parsing from bare array to paginated envelope (`items`, `total`, `next_cursor`)
- [ ] Add pagination support using `?cursor=` and `?limit=` query parameters
- [ ] Run your test suite and fix any remaining type or field mismatches

---

## Upgrade Command

```bash
pip install --upgrade zrb-cli>=2.0.0
```
