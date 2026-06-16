# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to address before upgrading.

---

## Breaking Changes

### 1. API endpoints are now prefixed with `/v2/`

All task endpoints moved under the `/v2/` prefix. Requests to the old paths will receive `404`.

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

Update your base URL or HTTP client prefix once and all endpoints inherit the change:

```python
# Before
client = httpx.Client(base_url="https://api.zrb.dev")

# After
client = httpx.Client(base_url="https://api.zrb.dev/v2")
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive `HTTP 401`.

**Before (v1):**

```http
GET /tasks
X-Auth-Token: abc123
```

**After (v2):**

```http
GET /v2/tasks
Authorization: Bearer abc123
```

In code:

```python
# Before
headers = {"X-Auth-Token": "abc123"}

# After
headers = {"Authorization": "Bearer abc123"}
```

If you rely on an HTTP client with built-in auth, switch to its Bearer token support:

```python
# Before
client = httpx.Client(headers={"X-Auth-Token": "abc123"})

# After
client = httpx.Client(auth=httpx.BearerAuth("abc123"))
```

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUID v4 strings instead of auto-incrementing integers. This affects URL parameters, response parsing, and any code that assumes numeric IDs.

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

Update any code that stores, compares, or serializes task IDs as integers:

```python
# Before
task_id: int = response["id"]
url = f"/tasks/{task_id}"

# After
task_id: str = response["id"]
url = f"/v2/tasks/{task_id}"
```

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored (not an error), but responses will no longer include `done`.

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

In code:

```python
# Before
task = client.get("/tasks/42")
if task["done"]:
    print("Task finished!")

# After
task = client.get("/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
if task["completed"]:
    print("Task finished!")
```

### 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `HTTP 422`.

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

In code:

```python
# Before
client.post("/tasks", json={"title": "Write tests"})

# After
client.post("/v2/tasks", json={
    "title": "Write tests",
    "project_id": "proj_abc123",
})
```

If your integration creates tasks without project context, you must assign a project ID first. Contact your workspace admin if you need a project created for your integration.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. The response is now an object with `items`, `total`, and `next_cursor`.

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
    {"id": "e5f67890-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetch subsequent pages by passing the cursor:

```python
# Before — single request, all results
tasks = client.get("/tasks").json()

# After — paginated fetching
def fetch_all_tasks(client):
    tasks = []
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/v2/tasks", params=params).json()
        tasks.extend(page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return tasks
```

You can also limit page size with `?limit=N` (default is 20).

---

## Migration Checklist

- [ ] Update base URL or endpoint prefix to include `/v2/`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer` header
- [ ] Change task ID handling from `int` to `str` (UUID)
- [ ] Rename all `done` field reads/writes to `completed`
- [ ] Add `project_id` to all task creation requests
- [ ] Update list endpoint response parsing: access `items` array instead of treating the response as a direct array
- [ ] Implement cursor-based pagination for list endpoints if you need more than 20 results per request
- [ ] Run integration tests against a v2 staging environment
- [ ] Remove any workarounds for v1 limitations that v2 addresses natively

---

## Upgrade

```bash
zrb upgrade --to v2
```