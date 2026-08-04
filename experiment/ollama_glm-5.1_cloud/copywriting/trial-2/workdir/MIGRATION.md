# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to handle, with before/after examples for each.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every v1 endpoint path has moved under `/v2/`. Requests to the old paths will return 404.

**Before (v1):**
```bash
curl https://api.zrb.dev/tasks
curl https://api.zrb.dev/tasks/42
```

**After (v2):**
```bash
curl https://api.zrb.dev/v2/tasks
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

If your code constructs URLs from a base path, change the base once:

**Before:**
```python
BASE_URL = "https://api.zrb.dev"
resp = requests.get(f"{BASE_URL}/tasks")
```

**After:**
```python
BASE_URL = "https://api.zrb.dev/v2"
resp = requests.get(f"{BASE_URL}/tasks")
```

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.dev/v2/tasks
```

**Before:**
```python
headers = {"X-Auth-Token": api_key}
```

**After:**
```python
headers = {"Authorization": f"Bearer {api_token}"}
```

---

### 3. Task `id` changed from integer to UUID string

All task IDs are now UUID strings instead of integers. Any code that stores, serializes, or validates task IDs as integers must be updated.

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

**Before:**
```python
task_id: int = response["id"]
```

**After:**
```python
task_id: str = response["id"]
```

If you store task IDs in a database, migrate the column type from integer to string before switching to v2.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is ignored (not an error), but it will not update the task.

**Before (v1):**
```json
{
  "title": "Ship release",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Ship release",
  "completed": true
}
```

**Before:**
```python
if task["done"]:
    mark_complete(task)
```

**After:**
```python
if task["completed"]:
    mark_complete(task)
```

---

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: your_api_key" \
  -d '{"title": "New task"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

**Before:**
```python
task = requests.post(f"{BASE_URL}/tasks", json={"title": "Write tests"})
```

**After:**
```python
task = requests.post(
    f"{BASE_URL}/tasks",
    json={"title": "Write tests", "project_id": "proj_abc123"},
)
```

You need a valid project ID before creating tasks. Obtain one from your project setup or the projects API.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an object with `items`, `total`, and `next_cursor`. This breaks any code that iterates the response directly as an array.

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

**Before:**
```python
tasks = requests.get(f"{BASE_URL}/tasks").json()
for task in tasks:
    print(task["title"])
```

**After:**
```python
def get_all_tasks():
    tasks = []
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        resp = requests.get(f"{BASE_URL}/tasks", params=params).json()
        tasks.extend(resp["items"])
        cursor = resp.get("next_cursor")
        if not cursor:
            break
    return tasks

for task in get_all_tasks():
    print(task["title"])
```

To fetch the next page, pass `?cursor=<next_cursor>`. Use `?limit=N` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs to include the `/v2/` prefix (or update the base URL constant).
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer` in all request headers.
- [ ] Change task ID handling from integer to UUID string — update type annotations, database columns, validation logic, and any hardcoded or fixture IDs.
- [ ] Rename all references to the `done` field to `completed` — in request bodies, response parsers, conditionals, and serializers.
- [ ] Add `project_id` to every task creation request; ensure a valid project ID is available before calling `POST /v2/tasks`.
- [ ] Refactor all list-endpoint consumers to read from the `items` key of the paginated envelope instead of treating the response as a bare array.
- [ ] Implement cursor-based pagination using `next_cursor` and the `?cursor=` query parameter if you need results beyond the first page.
- [ ] Run your test suite against the v2 API and verify every endpoint your integration uses.

---

Upgrade now:

```bash
zrb upgrade --to v2
```