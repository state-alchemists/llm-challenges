# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Several v1 fields and conventions have changed — this guide covers every breaking change and the code updates you need.

---

## Breaking Changes

### 1. API prefix added to all endpoints

Every endpoint now lives under `/v2/`. Requests to the old paths receive `404`.

**Before (v1)**

```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**

```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

The simplest migration is to set a base URL once in your HTTP client:

```python
# Before
BASE_URL = "https://api.zrb.dev"

# After
BASE_URL = "https://api.zrb.dev/v2"
```

### 2. Authentication header replaced

The `X-Auth-Token` header is no longer accepted. Requests using it receive `401 Unauthorized`. Use a standard `Authorization: Bearer` header instead.

**Before (v1)**

```python
import requests

resp = requests.get(
    "https://api.zrb.dev/tasks",
    headers={"X-Auth-Token": "sk_abc123"},
)
```

**After (v2)**

```python
import requests

resp = requests.get(
    "https://api.zrb.dev/v2/tasks",
    headers={"Authorization": "Bearer sk_abc123"},
)
```

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUID strings (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`) instead of auto-incrementing integers. Any code that stores, compares, or serializes task IDs as integers must be updated.

**Before (v1)**

```python
task = {
    "id": 42,
    "title": "Write tests",
    "done": False,
    "created_at": "2024-01-15T10:30:00Z",
}
# Storing in a dict keyed by int
tasks_by_id = {task["id"]: task}
```

**After (v2)**

```python
task = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "title": "Write tests",
    "completed": False,
    "project_id": "proj_abc123",
    "created_at": "2024-01-15T10:30:00Z",
}
# IDs are now strings — store as-is
tasks_by_id = {task["id"]: task}
```

If your database schema stores task IDs as `INTEGER`, run a migration to `VARCHAR` or `UUID` columns before inserting v2 data.

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. This affects both responses and update request bodies.

**Before (v1)**

```python
# Reading a task
if task["done"]:
    print("Task is finished")

# Updating a task
resp = requests.put(
    "https://api.zrb.dev/tasks/42",
    json={"done": True},
)
```

**After (v2)**

```python
# Reading a task
if task["completed"]:
    print("Task is finished")

# Updating a task
resp = requests.put(
    "https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    json={"completed": True},
)
```

Sending `"done": true` in a v2 update request will be silently ignored (not treated as `"completed": true`).

### 5. `project_id` is now required when creating tasks

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1)**

```python
resp = requests.post(
    "https://api.zrb.dev/tasks",
    json={"title": "New task title"},
)
```

**After (v2)**

```python
resp = requests.post(
    "https://api.zrb.dev/v2/tasks",
    json={
        "title": "New task title",
        "project_id": "proj_abc123",
    },
)
```

### 6. List endpoints return a paginated envelope

`GET /tasks` previously returned a bare JSON array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`. Any code that parses the response as a plain array will break.

**Before (v1)**

```python
resp = requests.get(
    "https://api.zrb.dev/tasks",
    headers={"X-Auth-Token": "sk_abc123"},
)
tasks = resp.json()  # bare array
for task in tasks:
    print(task["title"])
```

**After (v2)**

```python
resp = requests.get(
    "https://api.zrb.dev/v2/tasks",
    headers={"Authorization": "Bearer sk_abc123"},
)
body = resp.json()       # paginated envelope
tasks = body["items"]    # task array is inside "items"
for task in tasks:
    print(task["title"])

# Fetch subsequent pages
if body["next_cursor"]:
    resp = requests.get(
        "https://api.zrb.dev/v2/tasks",
        params={"cursor": body["next_cursor"]},
        headers={"Authorization": "Bearer sk_abc123"},
    )
```

To fetch all tasks, loop until `next_cursor` is `null`:

```python
def fetch_all_tasks():
    tasks = []
    cursor = None
    while True:
        resp = requests.get(
            "https://api.zrb.dev/v2/tasks",
            params={"cursor": cursor} if cursor else {},
            headers={"Authorization": "Bearer sk_abc123"},
        )
        body = resp.json()
        tasks.extend(body["items"])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return tasks
```

---

## Migration Checklist

- [ ] Update the base URL in your HTTP client to include the `/v2` prefix.
- [ ] Replace all `X-Auth-Token` headers with `Authorization: Bearer` headers.
- [ ] Change any code that stores task IDs as integers to use strings (UUID format).
- [ ] If you persist task IDs in a database, migrate the column type from `INTEGER` to `VARCHAR`/`UUID`.
- [ ] Rename all reads of `task["done"]` to `task["completed"]`.
- [ ] Rename all writes of `{"done": ...}` to `{"completed": ...}` in update requests.
- [ ] Add `project_id` to every task creation request.
- [ ] Update all list-response parsers to read `body["items"]` instead of treating the response body as a bare array.
- [ ] Implement cursor-based pagination using `next_cursor` and the `cursor` query parameter where you need to page through results.
- [ ] Run your integration tests against a v2 staging environment before switching production traffic.

---

## Upgrade

```bash
pip install --upgrade zrb
```