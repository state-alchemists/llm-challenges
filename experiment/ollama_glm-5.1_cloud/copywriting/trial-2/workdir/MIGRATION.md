# Migrating from Zrb v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Several v1 conventions have changed in ways that will break existing integrations if not updated. This guide covers every breaking change with before/after examples.

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every API path now starts with `/v2/`. Requests to the old paths will return 404.

**Before (v1):**

```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication header changed

The `X-Auth-Token` header is removed. Requests that use it receive HTTP 401. Replace it with a standard `Authorization: Bearer` header.

**Before (v1):**

```http
X-Auth-Token: your_api_key
```

**After (v2):**

```http
Authorization: Bearer your_api_token
```

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUIDs instead of auto-incrementing integers. Any code that parses, stores, or validates `id` as an integer must be updated.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**

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

The boolean field `done` is now `completed`. Sending `done` in a request body is ignored; reading `done` from a response will yield `undefined`.

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
  "title": "Ship v1",
  "completed": true
}
```

### 5. Task creation now requires `project_id`

Creating a task without `project_id` returns HTTP 422. You must include a valid project identifier in every `POST /v2/tasks` request.

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

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /tasks` previously returned a bare JSON array. It now returns an object with `items`, `total`, and `next_cursor`. Code that iterates over the top-level response must be updated to iterate over `response.items`. To fetch the next page, pass `?cursor=<next_cursor>`.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_def456", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API request paths to include the `/v2/` prefix
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer` in all clients and middleware
- [ ] Change task `id` handling from integer to UUID string (parsing, storage, validation, URL construction)
- [ ] Rename all references to the `done` field to `completed` (read paths and write paths)
- [ ] Add `project_id` to every task creation request and ensure your data model can store it
- [ ] Update list-response parsing to read from the `items` key instead of treating the response as a bare array
- [ ] Implement cursor-based pagination: consume `next_cursor` from responses and pass it as `?cursor=` on subsequent requests
- [ ] Remove any integer-based or offset-based pagination logic you built around the old list endpoint
- [ ] Run integration tests against a v2 staging environment before switching production traffic

## Upgrade

```bash
npm install zrb@2
```