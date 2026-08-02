# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change, with before/after examples and a migration checklist.

---

## Breaking Changes

### 1. Endpoint paths are now prefixed with `/v2/`

All endpoints moved under `/v2/`. Requests to the v1 paths will receive `404`.

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
GET /v2/tasks/<uuid>
POST /v2/tasks
PUT /v2/tasks/<uuid>
DELETE /v2/tasks/<uuid>
```

Update your base URL or request builder to prepend `/v2`.

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests carrying it will receive `401 Unauthorized`.

**Before (v1):**

```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key
```

**After (v2):**

```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token
```

If your HTTP client has a built-in bearer-token helper, prefer that over setting the header manually.

### 3. Task `id` changed from integer to UUID string

Every task ID is now a UUID. Any code that stores, compares, or URL-interpolates task IDs as integers must be updated.

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

**Impact:** database schemas, URL templates, and type definitions that declare `id` as `int` need to change to `str`/`string`. Route patterns matching `/tasks/:id` should accept UUIDs, not just digits.

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. The old name is not accepted in request bodies and does not appear in responses.

**Before (v1) — update a task:**

```json
PUT /tasks/42
{ "done": true }
```

**After (v2) — update a task:**

```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{ "completed": true }
```

**Before (v1) — read a task and check status (Python):**

```python
if task["done"]:
    print("Task finished")
```

**After (v2):**

```python
if task["completed"]:
    print("Task finished")
```

Search your codebase for `done` (including `"done"` in JSON/dict access) and replace each occurrence with `completed` in task-related code.

### 5. Task creation now requires `project_id`

`POST /v2/tasks` will return `422 Unprocessable Entity` if `project_id` is missing.

**Before (v1):**

```json
POST /tasks
{ "title": "New task title" }
```

**After (v2):**

```json
POST /v2/tasks
{ "title": "New task title", "project_id": "proj_abc123" }
```

You will need a known project ID before creating tasks. If your integration doesn't yet have one, create a project first (see the v2 Projects API) or obtain the ID from your dashboard.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "e5f6-7890-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Any code that iterates over the top-level response as an array must now iterate over `response["items"]`. For example:

**Before (v1) — Python:**

```python
tasks = requests.get("/tasks", headers=headers).json()
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
data = requests.get("/v2/tasks", headers=headers).json()
for task in data["items"]:
    print(task["title"])
```

To fetch all pages, use cursor-based pagination:

```python
cursor = None
all_tasks = []
while True:
    params = {"cursor": cursor} if cursor else {}
    data = requests.get("/v2/tasks", headers=headers, params=params).json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

1. **Update base URL** — prepend `/v2/` to all endpoint paths in your client code or configuration.
2. **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove any `X-Auth-Token` references.
3. **Update ID handling** — change task ID types from integer to UUID string in models, databases, URL patterns, and validators.
4. **Rename `done` → `completed`** — update all reads, writes, conditionals, and serialization that reference the `done` field.
5. **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request body includes a `project_id`.
6. **Unwrap paginated lists** — change code that treats the list response as a bare array to iterate over the `items` key instead. Implement cursor-based pagination if you need to fetch more than one page.
7. **Run integration tests** against the v2 API and verify all endpoints return the expected shapes.
8. **Update error handling** — v2 returns `401` for the old auth header and `422` for missing `project_id`. Adjust your error handling accordingly.

---

Upgrade now:

```bash
zrb upgrade --to v2
```