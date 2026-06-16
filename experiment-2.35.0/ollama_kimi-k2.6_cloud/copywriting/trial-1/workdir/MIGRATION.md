# Zrb Task API — v1 to v2 Migration Guide

Zrb CLI v2 introduces projects, paginated lists, and stricter authentication. This guide covers every breaking change and the concrete code changes required to migrate.

## Breaking Changes

### 1. Endpoint prefix changed to `/v2/`

All API paths are now version-prefixed. Calls to the old bare paths will return 404.

**v1 (before):**
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**v2 (after):**
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication header changed

`X-Auth-Token` is no longer accepted. Use a Bearer token instead. Requests sent with the old header will receive HTTP 401.

**v1 (before):**
```http
X-Auth-Token: <your_api_key>
```

**v2 (after):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` type changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any client-side code that assumes numeric IDs.

**v1 (before):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**v2 (after):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Task field `done` renamed to `completed`

The boolean status field is now called `completed`. Update deserialization and any request bodies that set the field.

**v1 (before):**
```json
{
  "done": true
}
```

**v2 (after):**
```json
{
  "completed": true
}
```

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` returns HTTP 422.

**v1 (before):**
```http
POST /tasks
```
```json
{
  "title": "New task title"
}
```

**v2 (after):**
```http
POST /v2/tasks
```
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

**v1 (before):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**v2 (after):**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Pass `?cursor=<next_cursor>` to fetch the next page.

## Migration Checklist

- [ ] Update the base URL or path prefix to `/v2/` on all endpoints.
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] Change task `id` handling from integer to UUID string.
- [ ] Rename every occurrence of the `done` field to `completed` in request and response handling.
- [ ] Add `project_id` to all task creation requests.
- [ ] Update list-task parsing to read the `items` array from the paginated envelope and handle `cursor`/`limit` query parameters.
- [ ] Run integration tests against the v2 endpoints.

## Upgrade

Install the latest v2 CLI:

```bash
pip install --upgrade zrb
```
