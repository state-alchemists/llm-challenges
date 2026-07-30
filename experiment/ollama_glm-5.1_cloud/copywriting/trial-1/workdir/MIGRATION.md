# Zrb Task API — Migrating from v1 to v2

This guide covers every breaking change between Zrb Task API v1 and v2. Read it end-to-end before starting your migration.

---

## Breaking Changes

### 1. Endpoint prefix `/v2/`

All endpoints are now prefixed with `/v2/`. The v1 paths (`/tasks`, `/tasks/{id}`) no longer exist.

**Before:**
```bash
curl -X GET https://api.example.com/tasks
curl -X POST https://api.example.com/tasks
curl -X GET  https://api.example.com/tasks/42
curl -X PUT  https://api.example.com/tasks/42
curl -X DELETE https://api.example.com/tasks/42
```

**After:**
```bash
curl -X GET https://api.example.com/v2/tasks
curl -X POST https://api.example.com/v2/tasks
curl -X GET  https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X PUT  https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

If your client constructs URLs from a base path, you may only need to update the base:

```python
# Before
BASE_URL = "https://api.example.com"

# After
BASE_URL = "https://api.example.com/v2"
```

---

### 2. Authentication header: `X-Auth-Token` → `Authorization: Bearer`

v2 replaces the custom `X-Auth-Token` header with the standard `Authorization: Bearer` scheme. Requests still using `X-Auth-Token` will receive **HTTP 401 Unauthorized**.

**Before:**
```bash
curl -H "X-Auth-Token: abc123" https://api.example.com/tasks
```

**After:**
```bash
curl -H "Authorization: Bearer abc123" https://api.example.com/v2/tasks
```

```python
# Before
headers = {"X-Auth-Token": api_key}

# After
headers = {"Authorization": f"Bearer {api_key}"}
```

---

### 3. Task `id` type: integer → UUID string

Task IDs are no longer auto-incrementing integers. They are now UUID strings (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`).

**Before:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

Any code that stores, compares, or serializes task IDs as integers must be updated:

```python
# Before — will break: UUIDs are not ints
task_id: int = task["id"]

# After
task_id: str = task["id"]
```

URL path parameters also change from `/tasks/42` to `/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`. If your route validation or OpenAPI schema constrains `{id}` to integers, update it to accept UUID strings.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The semantics are identical; only the key name changed.

**Before:**
```json
{"id": 42, "title": "Ship v1", "done": true, "created_at": "..."}
```

**After:**
```json
{"id": "a1b2c3d4-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
```

Update both read and write paths:

```python
# Before
if task["done"]:
    mark_completed()
task_update = {"done": True}

# After
if task["completed"]:
    mark_completed()
task_update = {"completed": True}
```

Sending `"done"` in a v2 request body will be silently ignored (or rejected, depending on the server's strictness), and reading `task["done"]` from v2 responses will raise a `KeyError`.

---

### 5. `project_id` is now required on task creation

v2 introduces a `project_id` field on every task. It is **required** when creating a task — omitting it returns **HTTP 422 Unprocessable Entity**.

**Before:**
```json
POST /tasks
{"title": "New task title"}
```

**After:**
```json
POST /v2/tasks
{"title": "New task title", "project_id": "proj_abc123"}
```

```python
# Before
payload = {"title": title}

# After
payload = {"title": title, "project_id": project_id}
```

If you do not yet have a project ID, you must create a project first (via the Projects API, outside the scope of this task endpoint reference) before you can create tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

v1 `GET /tasks` returned a bare JSON array. v2 wraps results in a pagination envelope with `items`, `total`, and `next_cursor`.

**Before (v1 response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 response):**
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

Any code that parses the response as a direct array will break. Update your client to extract `items` from the envelope:

```python
# Before
tasks = response.json()  # list directly

# After
body = response.json()
tasks = body["items"]
total = body["total"]
next_cursor = body.get("next_cursor")
```

To fetch the next page, pass the cursor as a query parameter:

```bash
curl "https://api.example.com/v2/tasks?cursor=cursor_xyz"
```

You can also set a page size with `?limit=N` (default is 20). To replicate the v1 behavior of fetching all tasks in a single request, you must now paginate through all cursors until `next_cursor` is `null`.

```python
# Paginated fetch loop
all_tasks = []
cursor = None

while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    resp = session.get("/v2/tasks", params=params)
    data = resp.json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2` prefix to all task endpoints (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer` on every request.
- [ ] **Update task ID handling** — change any `int` types, validations, or DB columns for task IDs to accept UUID strings.
- [ ] **Rename `done` → `completed`** — update read paths (response parsing) and write paths (request bodies).
- [ ] **Add `project_id` to task creation** — ensure all `POST /v2/tasks` requests include a `project_id`; handle HTTP 422 if missing.
- [ ] **Parse paginated envelope** — replace direct-array response parsing with `response["items"]` extraction; implement cursor-based pagination where needed.
- [ ] **Run integration tests** against a v2 staging environment to verify all changes.

---

## Upgrade

```bash
pip install --upgrade zrb
```