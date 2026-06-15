# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and shows exactly what to update in your code.

---

## Breaking Changes

### 1. Endpoint prefix: `/v2/` added to all routes

All endpoints now require the `/v2/` prefix. Requests to the old paths return 404.

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

Update any base-URL configuration rather than patching individual routes. For example:

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

### 2. Authentication header: `X-Auth-Token` → `Authorization: Bearer`

v2 no longer accepts `X-Auth-Token`. Requests using the old header receive HTTP 401.

**Before:**

```python
headers = {"X-Auth-Token": "sk_abc123"}
resp = requests.get(f"{BASE_URL}/tasks", headers=headers)
```

**After:**

```python
headers = {"Authorization": "Bearer sk_abc123"}
resp = requests.get(f"{BASE_URL}/tasks", headers=headers)
```

---

### 3. Task `id` changed from integer to UUID string

All task IDs are now UUID strings. Any code that parses, stores, or compares IDs as integers will break.

**Before:**

```python
task_id = resp.json()["id"]  # 42 (int)
# ...
resp = requests.get(f"{BASE_URL}/tasks/{task_id}")
```

**After:**

```python
task_id = resp.json()["id"]  # "a1b2c3d4-e5f6-7890-abcd-ef1234567890" (str)
# ...
resp = requests.get(f"{BASE_URL}/tasks/{task_id}")
```

If you store IDs in a database column, change the column type from `INTEGER` to `VARCHAR(36)` (or `UUID` if supported). If you use IDs as path parameters in your own routing, update the pattern from `<int:id>` to `<uuid:id>` (or the equivalent in your framework).

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Any code that reads or writes `done` will fail silently (or raise a key error).

**Before:**

```python
# Creating a task (no change — done was never sent on create)
# Updating a task
requests.put(
    f"{BASE_URL}/tasks/{task_id}",
    json={"done": True}
)

# Reading a task
is_done = task["done"]
```

**After:**

```python
# Updating a task
requests.put(
    f"{BASE_URL}/tasks/{task_id}",
    json={"completed": True}
)

# Reading a task
is_completed = task["completed"]
```

Do a project-wide search-and-replace for `"done"` in JSON payloads and dict keys. Be careful not to rename unrelated uses of the word "done".

---

### 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns HTTP 422.

**Before:**

```python
requests.post(
    f"{BASE_URL}/tasks",
    json={"title": "Write tests"}
)
```

**After:**

```python
requests.post(
    f"{BASE_URL}/tasks",
    json={"title": "Write tests", "project_id": "proj_abc123"}
)
```

You will need to know your project ID before creating tasks. Retrieve it from your project dashboard or the projects API.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a top-level array. It returns an envelope with `items`, `total`, and `next_cursor`.

**Before:**

```python
resp = requests.get(f"{BASE_URL}/tasks")
tasks = resp.json()  # list of task objects

for task in tasks:
    print(task["title"])
```

**After:**

```python
resp = requests.get(f"{BASE_URL}/tasks")
data = resp.json()  # {"items": [...], "total": 42, "next_cursor": "cursor_xyz"}

for task in data["items"]:
    print(task["title"])

# Fetch next page
if data.get("next_cursor"):
    resp = requests.get(
        f"{BASE_URL}/tasks",
        params={"cursor": data["next_cursor"]}
    )
```

Any code that assumes `resp.json()` is a list will raise a `TypeError`. Update deserialization and pagination logic. You can also pass `?limit=N` to control page size (default 20).

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2` prefix to the API base URL.
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Update ID handling** — change ID storage, comparisons, and path parameters from integer to UUID string.
- [ ] **Rename `done` → `completed`** — in request bodies and response parsing (both read and write paths).
- [ ] **Add `project_id` to task creation** — ensure all `POST /v2/tasks` calls include `project_id`.
- [ ] **Parse paginated envelope** — update list-endpoint consumers to read from `items` instead of treating the response as a bare array; implement cursor-based pagination where needed.
- [ ] **Run integration tests** against v2 to catch any remaining mismatches.
- [ ] **Update client SDKs** if you maintain generated or hand-written wrappers.

---

## Upgrade

```bash
pip install --upgrade zrb
```