# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Every change listed below breaks existing v1 integrations. This guide covers what changed, how to update your code, and a checklist to verify your migration.

---

## Breaking Changes

### 1. All endpoints moved under `/v2/` prefix

Every v1 endpoint path now requires a `/v2/` prefix. Requests to the old paths will receive `404`.

**Before:**
```bash
curl https://api.zrb.io/tasks
```

**After:**
```bash
curl https://api.zrb.io/v2/tasks
```

**Before:**
```python
import requests

resp = requests.get("https://api.zrb.io/tasks")
```

**After:**
```python
import requests

resp = requests.get("https://api.zrb.io/v2/tasks")
```

If you store the base URL in a config variable, you only need to update it once:

```python
BASE_URL = "https://api.zrb.io/v2"  # was /tasks → now /v2/tasks
```

---

### 2. Authentication header changed

v1 uses the `X-Auth-Token` header. v2 replaces it with a standard `Authorization: Bearer` header. Requests that send `X-Auth-Token` will receive `401 Unauthorized`.

**Before:**
```bash
curl -H "X-Auth-Token: abc123" https://api.zrb.io/tasks
```

**After:**
```bash
curl -H "Authorization: Bearer abc123" https://api.zrb.io/v2/tasks
```

**Before:**
```python
headers = {"X-Auth-Token": "abc123"}
resp = requests.get("https://api.zrb.io/tasks", headers=headers)
```

**After:**
```python
headers = {"Authorization": "Bearer abc123"}
resp = requests.get("https://api.zrb.io/v2/tasks", headers=headers)
```

---

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUIDs instead of auto-incrementing integers. Any code that parses, stores, or compares IDs as integers will break.

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

**Before:**
```python
task_id = response.json()["id"]  # int
assert isinstance(task_id, int)
```

**After:**
```python
task_id = response.json()["id"]  # str (UUID)
assert isinstance(task_id, str)
```

Update your database schemas, type annotations, and any URL construction that interpolates IDs:

**Before:**
```python
url = f"https://api.zrb.io/tasks/{task_id}"  # task_id was int
```

**After:**
```
url = f"https://api.zrb.io/v2/tasks/{task_id}"  # task_id is now UUID string
```

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored (not treated as `completed`). Reading `done` from a response will raise a `KeyError` if you access it directly.

**Before:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Before:**
```python
if task["done"]:
    print("Task finished!")
```

**After:**
```python
if task["completed"]:
    print("Task finished!")
```

**Before:**
```python
resp = requests.put(
    f"https://api.zrb.io/tasks/{task_id}",
    json={"title": "New title", "done": True},
)
```

**After:**
```python
resp = requests.put(
    f"https://api.zrb.io/v2/tasks/{task_id}",
    json={"title": "New title", "completed": True},
)
```

Do a project-wide search for the string `"done"` in API-related code and replace each occurrence with `"completed"`. Also check any ORM models, serializers, or type definitions that reference the old field name.

---

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`. v1 had no concept of projects — all tasks existed in a single global scope.

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

**Before:**
```python
resp = requests.post(
    "https://api.zrb.io/tasks",
    json={"title": "New task title"},
)
```

**After:**
```python
resp = requests.post(
    "https://api.zrb.io/v2/tasks",
    json={"title": "New task title", "project_id": "proj_abc123"},
)
```

If you need a default project, create one first and store its ID as a constant. All v1 tasks should be assigned to a project during migration.

---

### 6. List endpoints return a paginated envelope instead of a bare array

v1 returns a bare JSON array for `GET /tasks`. v2 returns a paginated envelope with `items`, `total`, and `next_cursor`. Any code that iterates the top-level response as an array will break.

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

**Before:**
```python
tasks = requests.get("https://api.zrb.io/tasks").json()
for task in tasks:
    print(task["title"])
```

**After:**
```python
tasks = requests.get("https://api.zrb.io/v2/tasks").json()["items"]
for task in tasks:
    print(task["title"])
```

To fetch all pages:

```python
url = "https://api.zrb.io/v2/tasks"
all_tasks = []

while url:
    data = requests.get(url, headers=headers).json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    url = f"https://api.zrb.io/v2/tasks?cursor={cursor}" if cursor else None
```

The default page size is 20. Use the `limit` query parameter to adjust it (e.g., `?limit=100`).

---

## Migration Checklist

- [ ] **Update base URL** — prepend `/v2/` to all endpoint paths, or update the base URL constant in your config.
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer` everywhere requests are made.
- [ ] **Update ID handling** — change task ID type from integer to string (UUID) in models, serializers, database columns, and type annotations.
- [ ] **Rename `done` to `completed`** — update request bodies, response parsers, and all downstream code that reads or writes the field.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`. Create a default project first if needed.
- [ ] **Unwrap paginated responses** — replace direct array iteration with `response["items"]`. Implement cursor-based pagination for complete result sets.
- [ ] **Search for hardcoded URLs** — grep for `/tasks` in config files, environment variables, and client libraries.
- [ ] **Run integration tests** — verify all CRUD operations work against the v2 API before cutting over production traffic.

---

## Upgrade

```bash
zrb upgrade --version 2
```