# Migration Guide: Zrb CLI v1 to v2

This guide covers every breaking change between v1 and v2 and how to update your integration.

## Overview

v2 introduces projects, cursor-based pagination, and stricter authentication. Six changes require updates in any v1 integration.

---

## Breaking Changes

### 1. Endpoint Prefix

All endpoints now carry a `/v2/` prefix.

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

### 2. Authentication Header

The auth header scheme changed from a custom header to a Bearer token.

**Before (v1)**
```http
X-Auth-Token: <your_api_key>
```

**After (v2)**
```http
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will receive `401 Unauthorized`.

---

### 3. Task ID Type

Task IDs are now UUID strings instead of integers.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "..." }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
```

Update any code that parses or stores task IDs to handle UUID strings. Database columns, foreign keys, and cache keys referencing task IDs must also be updated.

---

### 4. Field Renamed: `done` → `completed`

The boolean completion flag has been renamed.

**Before (v1)**
```json
{ "done": true }
```

**After (v2)**
```json
{ "completed": true }
```

Update all read and write operations referencing `done`.

---

### 5. Create Requires `project_id`

Task creation now requires a `project_id`. This is a new required field.

**Before (v1)**
```json
POST /tasks
{ "title": "New task title" }
```

**After (v2)**
```json
POST /v2/tasks
{ "title": "New task title", "project_id": "proj_abc123" }
```

Omitting `project_id` returns `422 Unprocessable Entity`. Obtain a `project_id` from the projects endpoint before creating tasks.

---

### 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a pagination envelope.

**Before (v1)**
```json
GET /tasks
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2)**
```json
GET /v2/tasks
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Access tasks as `response.items`. Use `response.next_cursor` with `?cursor=` to paginate. A `null` cursor means no more pages.

---

## Migration Checklist

- [ ] Update all endpoint URLs: prepend `/v2/` to every path
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Replace integer task ID handling with UUID string handling
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to every task creation request
- [ ] Update list response parsing: access `items[]` array instead of the root array
- [ ] Add pagination handling: extract `next_cursor` and loop with `?cursor=` param
- [ ] Update any database columns or cache keys that store task IDs (integer → UUID)
- [ ] Add `limit` query param support if you need pages larger than the default 20

---

## Upgrade Command

```bash
pip install zrb-cli --upgrade
```

For containerized environments:

```bash
docker pull zrb/zrb-cli:latest
```
