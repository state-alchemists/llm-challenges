# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and what you need to update.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every v1 endpoint path has moved under `/v2/`. Requests to the old paths will receive `404`.

**Before (v1):**

```bash
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```bash
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**What to do:** Update your base URL or path constants. If you configured a base URL like `https://api.example.com`, point it at `https://api.example.com/v2`. Alternatively, prepend `/v2` to every route string.

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it will receive `401 Unauthorized`.

**Before (v1):**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.example.com/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.example.com/v2/tasks
```

**What to do:** Replace all `X-Auth-Token` headers with `Authorization: Bearer <token>`. Update any HTTP client middleware, interceptors, or environment variables that inject the old header.

---

### 3. Task `id` changed from integer to UUID string

The `id` field on every task object is now a UUID string, not an integer. This affects path parameters in `GET`, `PUT`, and `DELETE` requests, as well as any code that stores, compares, or serializes task IDs.

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

**What to do:** Change any type annotations, schemas, or parsers that expect `id` to be an integer. Update route matchers that parse `:id` as a number. If you sort or index on `id`, switch to string-based ordering or a separate sequence field.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old name is no longer present in responses or accepted in request bodies.

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

**What to do:** Search your codebase for all references to the `done` field — in serializers, deserializers, conditional logic, tests, and mocks — and replace them with `completed`. Watch for places where `done` is a common word (e.g., "fetch done", "task is done") and only change the field access.

---

### 5. Creating a task now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

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

**What to do:** Ensure every task creation call includes a valid `project_id`. If you don't yet have projects, you'll need to create one first (see the v2 Projects API docs). Update request body types and validation to mark `project_id` as required.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare array. The response is now an envelope containing `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages.

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
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**What to do:** Update any code that parses the response as an array — it must now unwrap the `items` key. Implement cursor-based pagination if you need more than the default 20 results per page. Use the `limit` query parameter to adjust page size. If you previously relied on receiving all tasks in a single request, you must now loop over cursors until `next_cursor` is `null`.

**Paginating through all tasks:**

```python
cursor = None
all_tasks = []

while True:
    url = "https://api.example.com/v2/tasks?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    response = requests.get(url, headers=headers)
    data = response.json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

- [ ] Update all endpoint paths to include the `/v2/` prefix (or set a new base URL)
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task `id` handling from integer to UUID string (types, parsers, route matchers)
- [ ] Rename all `done` field references to `completed` (read and write paths)
- [ ] Add `project_id` to every task creation request body
- [ ] Update list endpoint response parsing from bare array to `items` / `total` / `next_cursor` envelope
- [ ] Implement cursor-based pagination where you need more than one page of results
- [ ] Update tests and mocks to reflect the new response shapes and headers
- [ ] Remove any fallback logic for v1 response formats

---

Upgrade now:

```bash
pip install --upgrade zrb
```