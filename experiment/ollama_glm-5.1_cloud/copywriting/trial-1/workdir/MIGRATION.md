# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes require updates to your client code. This guide walks through each one.

---

## Breaking Changes

### 1. API routes now require the `/v2/` prefix

All endpoint paths are now under `/v2/`. Requests to the old paths will 404.

**Before (v1)**

```bash
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**

```bash
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

If your code constructs URLs from a base path, update the base:

```python
# v1
BASE_URL = "https://api.zrb.dev"

# v2
BASE_URL = "https://api.zrb.dev/v2"
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive HTTP 401.

**Before (v1)**

```python
headers = {
    "X-Auth-Token": api_key,
}
```

**After (v2)**

```python
headers = {
    "Authorization": f"Bearer {api_key}",
}
```

If you share a central HTTP client or session object, update the header there — a single change covers all requests.

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUIDs, not auto-incrementing integers. This affects URL construction, response parsing, and any code that stores or compares IDs.

**Before (v1)**

```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2)**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

Update any type assertions, database schemas, or foreign keys that assume integer IDs:

```python
# v1
task_id: int = response["id"]

# v2
task_id: str = response["id"]
```

### 4. Field `done` renamed to `completed`

The boolean field `done` is now `completed`. The old name is not accepted in v2 request or response payloads.

**Before (v1)**

```python
# Creating/updating a task
payload = {"title": "Ship release", "done": True}

# Reading a task
is_done = task["done"]
```

**After (v2)**

```python
# Creating/updating a task
payload = {"title": "Ship release", "completed": True}

# Reading a task
is_completed = task["completed"]
```

Search your codebase for all references to the `done` field — property access, serialization aliases, query parameters, and test fixtures all need updating.

### 5. `project_id` is now required when creating a task

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP 422. This is a new mandatory concept — tasks must belong to a project.

**Before (v1)**

```python
payload = {"title": "New task title"}
response = requests.post(f"{BASE_URL}/v2/tasks", json=payload, headers=headers)
```

**After (v2)**

```python
payload = {"title": "New task title", "project_id": "proj_abc123"}
response = requests.post(f"{BASE_URL}/v2/tasks", json=payload, headers=headers)
```

If you don't yet have a project ID, create one first (or obtain it from your project admin). Any automated task-creation scripts must be updated to supply `project_id`.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates over the raw response array will break.

**Before (v1)**

```python
response = requests.get(f"{BASE_URL}/v2/tasks", headers=headers)
tasks = response.json()  # bare array

for task in tasks:
    print(task["title"])
```

**After (v2)**

```python
response = requests.get(f"{BASE_URL}/v2/tasks", headers=headers)
data = response.json()  # envelope
tasks = data["items"]

for task in tasks:
    print(task["title"])

# Fetch the next page
if data["next_cursor"]:
    next_response = requests.get(
        f"{BASE_URL}/v2/tasks?cursor={data['next_cursor']}",
        headers=headers,
    )
```

To retrieve all tasks, loop until `next_cursor` is `null`:

```python
all_tasks = []
cursor = None

while True:
    url = f"{BASE_URL}/v2/tasks"
    if cursor:
        url += f"?cursor={cursor}"
    resp = requests.get(url, headers=headers)
    data = resp.json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all API routes (or set a new `BASE_URL` constant).
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer` in your HTTP client, session, or middleware.
- [ ] **Update ID handling** — change task `id` from `int` to `str` (UUID) in models, schemas, foreign keys, and type hints.
- [ ] **Rename `done` → `completed`** — update all reads and writes of the `done` field in payloads, serializers, and tests.
- [ ] **Add `project_id` to task creation** — update every `POST /v2/tasks` call to include `project_id`; handle the 422 error case for missing values.
- [ ] **Parse paginated envelope** — replace direct array iteration with `data["items"]` access; implement cursor-based pagination where you need all results.
- [ ] **Run your test suite** — verify all integration tests pass against the v2 endpoints.

---

## Upgrade

```bash
pip install --upgrade zrb
```