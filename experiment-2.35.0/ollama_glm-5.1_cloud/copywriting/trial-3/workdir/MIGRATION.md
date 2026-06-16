# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes require updates to your client code. This guide covers each one with before/after examples and ends with a migration checklist.

## Breaking Changes

### 1. Endpoint URL prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths (e.g. `GET /tasks`) will receive a 404.

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

Update your base URL or path constants. If you use a single base URL, change it from `/` to `/v2/` and remove any manual `/tasks` overrides.

### 2. Authentication header

The `X-Auth-Token` header is removed. v2 uses standard Bearer token authentication. Requests that include `X-Auth-Token` will receive HTTP 401 Unauthorized.

**Before (v1):**

```http
X-Auth-Token: your_api_key
```

**After (v2):**

```http
Authorization: Bearer your_api_token
```

Replace your auth header logic. If you use an HTTP client with interceptors or middleware, update the header name and format there.

### 3. Task `id` type changed from integer to UUID string

Task IDs are now UUID strings instead of auto-incrementing integers. Any code that stores, compares, or serializes task IDs as integers must be updated.

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

Update any type definitions, database columns, or URL parameter parsers that expect an integer ID. Path parameters in route handlers must also accept UUID format.

### 4. Field `done` renamed to `completed`

The boolean field `done` on the task object is now `completed`. This affects both read responses and write request bodies.

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

Search your codebase for all references to the `done` field — conditionals, serializers, and update payloads — and rename them to `completed`.

### 5. `project_id` is now required when creating a task

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP 422 Unprocessable Entity.

**Before (v1):**

```json
{
  "title": "New task title"
}
```

**After (v2):**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Ensure every task creation call in your application supplies a valid `project_id`. If you have a single default project, store its ID as a constant and include it in all create requests.

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope containing `items`, `total`, and `next_cursor`. Clients that iterate directly over the response array must extract the `items` key first.

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
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

When `next_cursor` is absent or null, you have reached the last page. Update any code that assumed the response was a plain array, and implement cursor-based pagination if you need to fetch more than the default 20 results per page.

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all endpoint paths (or set the base URL to include `/v2/`)
- [ ] **Replace auth header** — switch from `X-Auth-Token` to `Authorization: Bearer`
- [ ] **Update ID types** — change task ID handling from integer to UUID string (type definitions, database columns, URL parameter parsers)
- [ ] **Rename `done` to `completed`** — update all read and write references to the task status field
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`
- [ ] **Parse paginated envelope** — update list response handling to read from `items` instead of treating the response as a bare array
- [ ] **Implement cursor pagination** — use `next_cursor` to fetch subsequent pages; handle `next_cursor` being absent to detect the last page
- [ ] **Run integration tests** — verify all CRUD operations against the v2 API
- [ ] **Remove v1 client code** — clean up any v1-specific fallbacks, types, or constants

## Upgrade

```bash
pip install --upgrade zrb
```