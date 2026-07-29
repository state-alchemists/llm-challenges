# Zrb CLI v1 to v2 Migration Guide

This guide covers every breaking change from v1 to v2 and how to update your integration.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication header changed

The auth header has changed from a custom header to a standard Bearer token.

**Before (v1)**
```
X-Auth-Token: <your_api_key>
```

**After (v2)**
```
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will now receive **HTTP 401**.

---

### 3. Task `id` type changed from integer to UUID string

Task IDs are no longer integers — they are now UUID strings.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", ... }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", ... }
```

Update any code that parses or stores task IDs to expect a string. URL path parameters for `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}` must now receive a UUID.

---

### 4. Task field `done` renamed to `completed`

The boolean status field has been renamed.

**Before (v1)**
```json
{ "done": true }
```

**After (v2)**
```json
{ "completed": true }
```

Rename `done` → `completed` in all request bodies, response parsing, and data models.

---

### 5. Task creation now requires `project_id`

The `project_id` field is now mandatory when creating a task. Omitting it returns **HTTP 422**.

**Before (v1)**
```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2)**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

All list responses are now wrapped in a pagination envelope. The array is no longer returned directly.

**Before (v1)**
```json
[
  { "id": 1, "title": "Buy milk", ... },
  { "id": 2, "title": "Ship v1", ... }
]
```

**After (v2)**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk", ... },
    { "id": "...", "title": "Ship v1", ... }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the same endpoint. Use the `limit` query parameter to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint paths from `/tasks` → `/v2/tasks`
- [ ] Change auth header from `X-Auth-Token` → `Authorization: Bearer <token>`
- [ ] Update task ID handling: integer → UUID string
- [ ] Rename all `done` fields to `completed` in request bodies and response parsing
- [ ] Add `project_id` to all task creation requests (required field)
- [ ] Update list response parsing: access `items[]` array from envelope, read `total` and `next_cursor` for pagination
- [ ] Update any URL path code that constructs task IDs (strings, not integers)
- [ ] Test with `HTTP 401` responses to confirm auth header is correct
- [ ] Test with `HTTP 422` responses to confirm `project_id` is being sent

---

## Upgrade Command

```bash
zrbacli upgrade
```
