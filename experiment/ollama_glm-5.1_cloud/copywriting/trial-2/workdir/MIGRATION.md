# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes require action before your integration will work against the new API. This guide covers each one with before/after examples, then provides a step-by-step checklist.

---

## Breaking Changes

### 1. All endpoints moved under `/v2/` prefix

Every endpoint path now starts with `/v2/`. Requests to the old paths will fail.

**Before (v1):**

```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

If you construct URLs dynamically, update your base path from `/tasks` to `/v2/tasks`.

### 2. Authentication header changed

The `X-Auth-Token` header is removed. Sending it will result in a `401 Unauthorized` response. Use the standard `Authorization` header with a `Bearer` token instead.

**Before (v1):**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.example.com/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.example.com/v2/tasks
```

### 3. Task `id` type changed from integer to UUID string

Task IDs are no longer auto-incremented integers. They are now UUID strings.

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

Any code that assumes `id` is an integer (e.g., type checks, sorting by numeric ID, URL patterns matching `\d+`) must be updated to handle UUID strings.

### 4. Field `done` renamed to `completed`

The boolean field indicating task completion is now called `completed`.

**Before (v1):**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Updated title",
  "completed": true
}
```

This affects both request bodies (on `PUT /tasks/{id}`) and response objects. Any code that reads or writes the `done` field must be updated to use `completed` instead.

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

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

You will need to know the project ID before creating a task. Plan your integration flow accordingly — if you were creating tasks without a project context, you must first create or look up a project.

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope object.

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
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination:**

- Use `?cursor=<next_cursor>` to fetch the next page.
- Use `?limit=<n>` to control page size (default 20).
- When `next_cursor` is `null` or absent, you have reached the last page.

Code that parses the response as a plain array must be updated to extract `items` from the envelope. If you need all results at once, you must loop through pages using the cursor.

---

## Migration Checklist

- [ ] **Update base URL path** — change `/tasks` to `/v2/tasks` in your HTTP client, route definitions, and any URL builders.
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer` in all requests. Remove any `X-Auth-Token` references.
- [ ] **Update ID handling** — change task ID types from integer to string (UUID). Update type definitions, validators, URL patterns, and any code that sorts or compares IDs numerically.
- [ ] **Rename `done` to `completed`** — update all references in serializers, deserializers, models, and consuming code.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id` field. Update your integration to obtain a project ID before creating tasks.
- [ ] **Parse paginated envelope** — update list-endpoint consumers to read from the `items` key. Implement cursor-based pagination where you need to fetch all results.

---

## Upgrade

```bash
pip install --upgrade zrb
```