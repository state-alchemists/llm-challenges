# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and provides before/after examples so you can update your integration with confidence.

---

## Breaking Changes

### 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths will receive `404`.

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
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Migration tip:** If your client uses a base URL, you only need to change it once:

```python
# Before
BASE_URL = "https://api.zrb.dev"

# After
BASE_URL = "https://api.zrb.dev/v2"
```

### 2. Authentication Header

The `X-Auth-Token` header is removed. v2 uses a standard `Authorization: Bearer` header. Requests that still send `X-Auth-Token` will receive `401 Unauthorized`.

**Before (v1):**

```python
headers = {
    "X-Auth-Token": "sk_live_abc123",
}
```

**After (v2):**

```python
headers = {
    "Authorization": "Bearer sk_live_abc123",
}
```

### 3. Task ID Type: Integer → UUID

Task `id` has changed from an auto-incrementing integer to a UUID string. Any code that parses, stores, or validates task IDs must be updated.

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

**Common code impact:**

```python
# Before — integer lookup
task_id = int(request.args["id"])

# After — string UUID lookup
task_id = request.args["id"]  # keep as string
```

If you store task IDs in a database, change the column type from `INTEGER` to `VARCHAR(36)` (or the equivalent in your database).

### 4. Field Rename: `done` → `completed`

The boolean field `done` has been renamed to `completed`. The old name is not accepted in request bodies and does not appear in response bodies.

**Before (v1):**

```python
# Creating/updating a task
payload = {"title": "Ship release", "done": True}

# Reading a task
if task["done"]:
    print("Already done")
```

**After (v2):**

```python
# Creating/updating a task
payload = {"title": "Ship release", "completed": True}

# Reading a task
if task["completed"]:
    print("Already completed")
```

### 5. Required Field: `project_id` on Task Creation

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

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

If your integration doesn't yet have a concept of projects, create a default project via the v2 API first, then pass its `project_id` on every task creation call.

### 6. Paginated List Response

`GET /v2/tasks` no longer returns a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`. You must update any code that expects a top-level array.

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
    {"id": "e5f6-7890-...", "title": "Ship v2", "completed": true, "project_id": "proj_xyz789", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:

```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

When `next_cursor` is `null` or absent, you have reached the last page.

**Before (v1) — client code:**

```python
tasks = requests.get(f"{BASE_URL}/tasks", headers=headers).json()
# tasks is a list
for task in tasks:
    process(task)
```

**After (v2) — client code:**

```python
url = f"{BASE_URL}/tasks"
while url:
    data = requests.get(url, headers=headers).json()
    for task in data["items"]:
        process(task)
    cursor = data.get("next_cursor")
    url = f"{BASE_URL}/tasks?cursor={cursor}" if cursor else None
```

---

## Migration Checklist

Work through each item before deploying your v2 integration:

- [ ] **Update base URL** — add `/v2` prefix (or set a new base URL constant).
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Change task ID handling** — update parsers, validators, and database columns from `INTEGER` to `VARCHAR(36)` / string UUID.
- [ ] **Rename `done` to `completed`** — in request bodies, response parsers, conditionals, and any serialized storage.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` includes a valid `project_id`. Create a default project if needed.
- [ ] **Handle paginated list responses** — update list-consuming code to unwrap `items` from the envelope and paginate with `cursor`.
- [ ] **Remove `X-Auth-Token` fallback** — v2 will reject it with `401`; clean up any dual-header code.
- [ ] **Run integration tests** against a v2 staging environment before switching production traffic.

---

## Upgrade

```
zrb upgrade --to v2
```