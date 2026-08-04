# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements require changes to any client currently targeting v1. This guide covers every breaking change with before/after examples and a migration checklist.

---

## Breaking Changes

### 1. Endpoint prefix: all routes now live under `/v2/`

Every endpoint path now starts with `/v2/`. Requests to the v1 paths will receive `404 Not Found`.

**Before (v1)**

```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**

```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update your base URL from `/` to `/v2/`, or set it once in your HTTP client configuration and let it propagate.

---

### 2. Authentication header changed

The custom `X-Auth-Token` header is removed. v2 uses a standard `Authorization: Bearer` header. Requests that still send `X-Auth-Token` will receive `401 Unauthorized`.

**Before (v1)**

```http
GET /tasks
X-Auth-Token: your_api_key
```

**After (v2)**

```http
GET /v2/tasks
Authorization: Bearer your_api_token
```

If you wrap requests in a helper, update it there. If you pass the key through an SDK option, look for an `api_key` or `token` parameter — most SDKs send `Bearer` by default.

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of integers. Any code that stores, compares, or serializes task IDs as numbers must treat them as strings.

**Before (v1)**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Affected areas:

- Database columns — change from `INTEGER` to `VARCHAR(36)` or `UUID`.
- URL path parameters — ensure your router treats `{id}` as a string, not an int.
- Equality checks — `"42"` (string) is not `42` (int); update any `==` / `.equals()` logic.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored; reading `.done` from a response will be `undefined`.

**Before (v1)**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2)**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Update every place you read or write this field — request bodies, response parsers, database mappings, and UI labels.

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1)**

```json
{
  "title": "New task title"
}
```

**After (v2)**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

You will need a project to create tasks under. If you do not yet have one, create it via the Projects API (see v2 spec) first, then pass the returned `project_id` when creating tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. The response is now an object with `items`, `total`, and `next_cursor`. Parse the `items` array for the task list and use `next_cursor` for subsequent pages.

**Before (v1)**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetch the next page with:

```http
GET /v2/tasks?cursor=cursor_xyz
```

Clients that previously parsed the response as `response` directly must now parse `response.items`. If you previously checked `response.length`, check `response.total` instead.

---

## Migration Checklist

- [ ] Update base URL to include `/v2/` prefix
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer` header
- [ ] Change task ID handling from integer to string (databases, routers, serializers, equality checks)
- [ ] Rename `done` field to `completed` in all request bodies and response parsers
- [ ] Add `project_id` to all task creation requests; ensure a project exists first
- [ ] Update list-endpoint response parsing from bare array to `items` / `total` / `next_cursor` envelope
- [ ] Add cursor-based pagination support where you previously iterated the full response
- [ ] Run integration tests against the v2 API before deploying

---

## Upgrade

```bash
npm install zrb@2
```