# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and shows you exactly what to update.

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every endpoint path now starts with `/v2/`. Requests to the old paths (e.g. `GET /tasks`) will return `404`.

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

> **Tip:** If you construct URLs dynamically, update your base path constant from `""` to `"/v2"` so the prefix applies everywhere at once.

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it will receive `HTTP 401`.

**Before (v1):**

```http
GET /tasks
X-Auth-Token: your_api_key
```

**After (v2):**

```http
GET /v2/tasks
Authorization: Bearer your_api_token
```

```python
# v1
headers = {"X-Auth-Token": api_key}

# v2
headers = {"Authorization": f"Bearer {api_key}"}
```

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Any code that parses, validates, or stores `id` as an integer must be updated.

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

```python
# v1
task_id: int = task["id"]

# v2
task_id: str = task["id"]
```

If you store task IDs in a database column, migrate the column type from `INTEGER` to `VARCHAR(36)` (or the equivalent UUID type for your database).

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is ignored — it will not toggle the task status.

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

```python
# v1
if task["done"]:
    ...

# v2
if task["completed"]:
    ...
```

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `HTTP 422`.

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

```python
# v1
requests.post("/tasks", json={"title": "Write tests"})

# v2
requests.post("/v2/tasks", json={"title": "Write tests", "project_id": "proj_abc123"})
```

You will need to determine the appropriate `project_id` for each task before migrating. List your projects first, then map existing tasks to the correct project.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope object containing `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages.

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
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_def456", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```python
# v1 — naive single-request fetch
tasks = requests.get("/tasks", headers=headers).json()
# tasks is a list

# v2 — paginated fetch
def fetch_all_tasks():
    tasks = []
    url = "/v2/tasks"
    while url:
        resp = requests.get(url, headers=headers).json()
        tasks.extend(resp["items"])
        cursor = resp.get("next_cursor")
        url = f"/v2/tasks?cursor={cursor}" if cursor else None
    return tasks
```

## Migration Checklist

- [ ] **Update base URL** — Change your API base path to include `/v2` (e.g. `https://api.example.com/v2`).
- [ ] **Switch auth header** — Replace `X-Auth-Token` with `Authorization: Bearer`. Remove any code referencing the old header.
- [ ] **Migrate task ID handling** — Update all ID storage, validation, and serialization from integer to UUID string. Change database columns if applicable.
- [ ] **Rename `done` to `completed`** — Update every read and write of the `done` field — response parsing, update requests, conditionals, and tests.
- [ ] **Add `project_id` to task creation** — Determine the correct project for each task and include `project_id` in all `POST /v2/tasks` request bodies.
- [ ] **Handle paginated list responses** — Replace code that expects a bare array with code that unwraps the `items` key and follows `next_cursor` cursors to fetch all pages.
- [ ] **Run integration tests** — Confirm every endpoint works end-to-end against a v2 test instance before switching production traffic.

## Upgrade

```bash
zrb upgrade --to v2
```