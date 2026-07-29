# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to handle, with before/after examples for each.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every URL path gains a `/v2/` prefix. Requests to the old paths will return `404`.

**Before (v1):**

```bash
curl https://api.example.com/tasks
curl https://api.example.com/tasks/42
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests that use it receive `401 Unauthorized`.

**Before (v1):**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.example.com/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.example.com/v2/tasks
```

### 3. Task `id` type changed from integer to UUID string

Task IDs are now UUID strings instead of integers. Any code that stores, compares, or serializes IDs as numbers must be updated to handle strings.

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

This also means URL path parameters change:

**Before (v1):**

```bash
curl https://api.example.com/tasks/42
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task field `done` renamed to `completed`

The boolean field `done` on the task object is now called `completed`. This affects both read responses and update request bodies.

**Before (v1) — reading a task:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — reading a task:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1) — marking a task done:**

```bash
curl -X PUT https://api.example.com/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2) — marking a task completed:**

```bash
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

### 5. Task creation now requires `project_id`

The `project_id` field is required on `POST /v2/tasks`. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages and `?limit=<n>` to control page size (default 20).

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

Code that iterates over the response directly must now iterate over `response.items`. Code that assumed a single request returns all results must implement cursor-based pagination:

```bash
# Fetch first page
curl "https://api.example.com/v2/tasks?limit=20"

# Fetch next page using the cursor from the previous response
curl "https://api.example.com/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

- [ ] **Update all endpoint URLs** — add the `/v2/` prefix to every API path (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).
- [ ] **Switch authentication header** — replace `X-Auth-Token` with `Authorization: Bearer` in all clients, SDKs, and configuration files.
- [ ] **Update ID handling** — change any code that treats task IDs as integers (database columns, type annotations, comparisons, routing) to use UUID strings instead.
- [ ] **Rename `done` to `completed`** — update all task reads, writes, conditionals, and serialization that reference the `done` field.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`. Determine which project each task belongs to and pass it accordingly.
- [ ] **Parse paginated envelope for list responses** — update all list-response consumers to read from `response.items` instead of treating the response body as a direct array. Implement cursor-based pagination using `next_cursor` and the `cursor` query parameter.
- [ ] **Remove reliance on `X-Auth-Token`** — search codebases for the old header name and delete or replace it; requests using it will receive `401`.
- [ ] **Test against v2** — run integration tests against the v2 API before switching production traffic.

---

## Upgrade

```bash
npm install zrb@2
```