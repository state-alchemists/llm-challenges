# Migrating from Zrb v1 to v2

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. These changes require updates to any client currently targeting the v1 API. This guide covers every breaking change with before/after examples and a migration checklist.

---

## Breaking Changes

### 1. API endpoint prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths return 404.

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

If your base URL was previously `https://api.zrb.io`, update it to `https://api.zrb.io/v2` so you only change it in one place.

---

### 2. Authentication header

The `X-Auth-Token` header is removed. Requests carrying it receive HTTP 401. Use a standard `Authorization: Bearer` header instead.

**Before (v1):**

```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key
```

```python
# Python — requests
headers = {"X-Auth-Token": "your_api_key"}
```

**After (v2):**

```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token
```

```python
# Python — requests
headers = {"Authorization": "Bearer your_api_token"}
```

---

### 3. Task ID type changed from integer to UUID string

Task `id` is now a UUID string, not an integer. Any code that parses, stores, or validates `id` as an integer must be updated.

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
# Python — storing or referencing a task
task_id = response["id"]          # int, e.g. 42
url = f"/tasks/{task_id}"          # /tasks/42
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
# Python — storing or referencing a task
task_id = response["id"]          # str, e.g. "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
url = f"/v2/tasks/{task_id}"      # /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update database schemas, type annotations, and validation rules accordingly. Also check any URL routing or path-building code that assumed numeric IDs.

---

### 4. Field renamed: `done` → `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored (not an error), but it will not update the task.

**Before (v1):**

```json
{
  "title": "Ship v2",
  "done": true
}
```

```python
# Python — checking task status
if task["done"]:
    print("Task is finished")
```

**After (v2):**

```json
{
  "title": "Ship v2",
  "completed": true
}
```

```python
# Python — checking task status
if task["completed"]:
    print("Task is finished")
```

Search your codebase for all reads and writes of the `done` field — conditions, serializers, database columns, and test fixtures all need updating.

---

### 5. `project_id` is now required on task creation

Creating a task without `project_id` returns HTTP 422. This is a new required field.

**Before (v1):**

```json
{
  "title": "New task title"
}
```

```python
# Python — requests
payload = {"title": "New task title"}
requests.post("https://api.zrb.io/v2/tasks", json=payload, headers=headers)
```

**After (v2):**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

```python
# Python — requests
payload = {"title": "New task title", "project_id": "proj_abc123"}
requests.post("https://api.zrb.io/v2/tasks", json=payload, headers=headers)
```

If your application does not already have a concept of projects, you will need to create at least one project via the v2 API (or the Zrb dashboard) and use its `project_id` when creating tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates the response directly as an array will break.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
# Python — iterating results
tasks = requests.get("https://api.zrb.io/tasks", headers=headers).json()
for task in tasks:
    print(task["title"])
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

```python
# Python — iterating results
data = requests.get("https://api.zrb.io/v2/tasks", headers=headers).json()
for task in data["items"]:
    print(task["title"])

# To fetch the next page:
if data["next_cursor"]:
    next_data = requests.get(
        f"https://api.zrb.io/v2/tasks?cursor={data['next_cursor']}",
        headers=headers,
    ).json()
```

Any code that accesses the response as a top-level array — loops, serializers, length checks — must be updated to access `response["items"]` instead. You may also want to add pagination logic using `next_cursor` and `limit`.

---

## Migration Checklist

Use this checklist to ensure your client is fully updated for v2:

- [ ] Update base URL to include `/v2` prefix (e.g. `https://api.zrb.io/v2`)
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Remove all references to `X-Auth-Token`; verify no middleware or interceptors still send it
- [ ] Change task `id` handling from integer to UUID string — update type annotations, database columns, and validation
- [ ] Rename all reads and writes of `done` to `completed` — including conditions, serializers, and test fixtures
- [ ] Add `project_id` to every task creation request
- [ ] Create a default project (via the Zrb dashboard or API) if you do not yet have one
- [ ] Update list-endpoint parsing: access `response["items"]` instead of treating the response as a bare array
- [ ] Add pagination logic: use `next_cursor` and `limit` query parameters where needed
- [ ] Run your integration test suite against the v2 API to confirm all changes

---

## Upgrade

```bash
zrb upgrade --to v2
```