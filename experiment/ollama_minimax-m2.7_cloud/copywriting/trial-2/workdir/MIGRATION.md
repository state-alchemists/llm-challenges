# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, improved pagination, and stricter authentication. Several v1 conventions are breaking changes — this guide covers every one with before/after examples.

---

## Breaking Changes

### 1. Endpoint Prefix Changed from `/tasks` to `/v2/tasks`

All endpoints now live under the `/v2/` prefix. Requests to v1 paths return `404`.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. v2 uses Bearer token authentication.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

Requests with `X-Auth-Token` will receive `401 Unauthorized`.

---

### 3. Task `id` Type Changed from Integer to UUID String

Task IDs are no longer sequential integers — they are now UUID strings.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

Update any code that parses or stores task IDs to expect a string. URL parameters for `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}` now take UUID strings.

---

### 4. Task Field `done` Renamed to `completed`

The boolean completion flag has been renamed.

**Before (v1)**
```json
{ "done": true }
```

**After (v2)**
```json
{ "completed": true }
```

Update all `done` references in request bodies, response parsing, and any persisted task state.

---

### 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` returns `422 Unprocessable Entity`.

**Before (v1)**
```http
POST /tasks
Content-Type: application/json

{ "title": "New task title" }
```

**After (v2)**
```http
POST /v2/tasks
Content-Type: application/json

{ "title": "New task title", "project_id": "proj_abc123" }
```

Obtain a `project_id` before creating tasks. See your project dashboard or use the projects endpoint to list available projects.

---

### 6. List Response Changed from Bare Array to Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1)**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2)**
```json
{
  "items": [
    { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To paginate, pass `?cursor=<next_cursor>` on the next request. Set `?limit=<n>` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Update task ID parsing to expect UUID strings instead of integers
- [ ] Rename all `done` field references to `completed` in request bodies and response handling
- [ ] Add `project_id` field to all task creation requests
- [ ] Update list response parsing to unwrap the `items` array from the envelope
- [ ] Implement cursor-based pagination for list operations
- [ ] Update any persisted task data that references `done` or integer IDs
- [ ] Run integration tests against the v2 endpoint

---

## Upgrade Command

```bash
pip install zrb==2.0.0
```

For projects using a `requirements.txt` or `pyproject.toml`, update the version constraint accordingly.