# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and what you need to update in your client code.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every endpoint path changes. The root `/tasks` becomes `/v2/tasks`, and so on for every resource.

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

If you construct URLs dynamically, update your base path constant:

**Before:**

```python
BASE_URL = "https://api.zrb.dev"
task_url = f"{BASE_URL}/tasks/{task_id}"
```

**After:**

```python
BASE_URL = "https://api.zrb.dev/v2"
task_url = f"{BASE_URL}/tasks/{task_id}"
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive **HTTP 401 Unauthorized**.

**Before (v1):**

```bash
curl -H "X-Auth-Token: abc123" https://api.zrb.dev/tasks
```

```python
import requests

resp = requests.get(
    "https://api.zrb.dev/tasks",
    headers={"X-Auth-Token": api_key},
)
```

**After (v2):**

```bash
curl -H "Authorization: Bearer abc123" https://api.zrb.dev/v2/tasks
```

```python
import requests

resp = requests.get(
    "https://api.zrb.dev/v2/tasks",
    headers={"Authorization": f"Bearer {api_key}"},
)
```

### 3. Task `id` type changed from integer to UUID string

Task IDs are now UUIDs (`"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`) instead of auto-incrementing integers (`42`). Any code that stores, compares, or logs IDs as integers must be updated.

**Before (v1):**

```python
task = {"id": 42, "title": "Write tests", "done": False, "created_at": "..."}
# Storing in a DB column typed as INTEGER
db.execute("INSERT INTO tasks (id, title) VALUES (?, ?)", (task["id"], task["title"]))
```

**After (v2):**

```python
task = {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": False, "project_id": "proj_abc123", "created_at": "..."}
# Storing in a DB column typed as VARCHAR/VARCHAR(36)
db.execute("INSERT INTO tasks (id, title) VALUES (?, ?)", (task["id"], task["title"]))
```

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now called `completed`. This affects both the response objects you read and the request bodies you send for updates. Sending `"done": true` in an update request will be silently ignored or cause a validation error.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```python
# Updating a task
resp = requests.put(
    f"{BASE_URL}/tasks/{task_id}",
    json={"done": True},
)
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
# Updating a task
resp = requests.put(
    f"{BASE_URL}/tasks/{task_id}",
    json={"completed": True},
)
```

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

```python
resp = requests.post(
    f"{BASE_URL}/tasks",
    json={"title": "New task title"},
)
```

**After (v2):**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

```python
resp = requests.post(
    f"{BASE_URL}/tasks",
    json={"title": "New task title", "project_id": "proj_abc123"},
)
```

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Use the `cursor` and `limit` query parameters to paginate.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
resp = requests.get(f"{BASE_URL}/tasks", headers=headers)
tasks = resp.json()  # directly a list
for task in tasks:
    print(task["title"])
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

```python
tasks = []
cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    resp = requests.get(f"{BASE_URL}/tasks", headers=headers, params=params)
    data = resp.json()
    tasks.extend(data["items"])
    if not data["next_cursor"]:
        break
    cursor = data["next_cursor"]

for task in tasks:
    print(task["title"])
```

---

## Migration Checklist

- [ ] Update your base URL to include the `/v2/` prefix (e.g. `https://api.zrb.dev/v2`)
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer` in all request headers
- [ ] Change any ID storage, comparison, or serialization from integer to UUID string (update DB column types, type annotations, and validation logic)
- [ ] Rename all references to the `done` field to `completed` — in response handling, update payloads, tests, and documentation
- [ ] Add `project_id` to every task creation request; ensure callers supply a valid project ID
- [ ] Update list-endpoint response handling to unwrap the `items` array from the paginated envelope (`resp["items"]` instead of `resp`)
- [ ] Implement cursor-based pagination: read `next_cursor` from responses, pass it as `?cursor=` on subsequent requests
- [ ] Run your integration test suite against the v2 API and fix any remaining failures

---

Upgrade to v2:

```bash
npm install zrb@2
```