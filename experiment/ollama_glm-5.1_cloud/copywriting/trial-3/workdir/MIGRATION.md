# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements come with **six breaking changes** that require code updates before upgrading.

## Breaking Changes

### 1. Authentication header changed

The `X-Auth-Token` header is removed. v2 uses a standard `Authorization: Bearer` header instead. Requests that include `X-Auth-Token` will receive **HTTP 401 Unauthorized**.

**Before:**

```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key
```

**After:**

```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token
```

### 2. All endpoints are prefixed with `/v2/`

Every endpoint path now begins with `/v2/`. Requests to the old paths (e.g., `GET /tasks`) will return 404.

**Before:**

```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After:**

```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 3. Task `id` changed from integer to UUID string

Task IDs are no longer auto-incremented integers. v2 assigns a UUID string to each task. Any code that stores, validates, or constructs URLs from task IDs must handle strings instead of numbers.

**Before:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

If your database or client code stores task IDs as integer columns, migrate them to `VARCHAR`/`TEXT` before pointing at v2.

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old name is no longer accepted in request bodies and will not appear in responses.

**Before (update request):**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (update request):**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Search your codebase for all references to the `done` field — in serializers, destructuring patterns, and conditional logic — and replace them with `completed`.

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` now returns **HTTP 422 Unprocessable Entity**. Every `POST /v2/tasks` request must include a `project_id` string identifying the project the task belongs to.

**Before:**

```json
{
  "title": "New task title"
}
```

**After:**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

If your integration creates tasks without a project context, you must first create or look up a project and then pass its ID.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a top-level JSON array. It now returns an object with `items`, `total`, and `next_cursor` fields. Clients that parse the response as an array will break.

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
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`. You can also set `?limit=<n>` (default 20). When `next_cursor` is `null`, you have reached the last page.

## Migration Checklist

- [ ] **Update the authentication header** — replace all `X-Auth-Token` headers with `Authorization: Bearer`. Remove any code that sets `X-Auth-Token`.
- [ ] **Update endpoint paths** — add the `/v2/` prefix to every request URL (`/tasks` → `/v2/tasks`, etc.).
- [ ] **Change task ID handling** — update type annotations, database columns, URL builders, and validators to accept UUID strings instead of integers.
- [ ] **Rename `done` to `completed`** — update all request bodies, response parsers, and client-side references.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`. Create or retrieve a project ID beforehand if needed.
- [ ] **Parse the paginated envelope** — update list-response parsing to read `items` from the envelope object instead of treating the response as a bare array. Implement cursor-based pagination using `next_cursor` and `limit`.

## Upgrade

```bash
npm install zrb@2
```