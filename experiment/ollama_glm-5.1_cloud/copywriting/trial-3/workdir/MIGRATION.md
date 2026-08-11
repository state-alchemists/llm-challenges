# Zrb CLI v1 → v2 Migration Guide

This guide covers everything you need to know to migrate from the Zrb Task API v1 to v2. v2 introduces projects, cursor-based pagination, and stricter authentication. Read through each breaking change, update your code accordingly, and then follow the checklist at the bottom.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every API path now starts with `/v2/`. Requests to the old `/tasks` routes will return `404`.

**Before:**

```bash
curl -X GET https://api.zrb.dev/tasks
```

**After:**

```bash
curl -X GET https://api.zrb.dev/v2/tasks
```

This applies to **all** endpoints — `GET`, `POST`, `PUT`, and `DELETE`.

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Sending it will result in an HTTP `401 Unauthorized` response.

**Before:**

```bash
curl -H "X-Auth-Token: abc123" https://api.zrb.dev/tasks
```

**After:**

```bash
curl -H "Authorization: Bearer abc123" https://api.zrb.dev/v2/tasks
```

If you use a client library or SDK, look for an authentication configuration option and switch from token-based to Bearer-based auth.

---

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUID strings instead of integers. Any code that stores, compares, or serializes IDs as integers will break.

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

**Impact on code that references tasks by ID:**

```python
# Before — integer ID
task_id = 42
resp = requests.get(f"https://api.zrb.dev/tasks/{task_id}")

# After — UUID string ID
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
resp = requests.get(f"https://api.zrb.dev/v2/tasks/{task_id}")
```

Update any database columns, type definitions, or URL builders that assume integer IDs.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. Sending `done` in a request body will be silently ignored (not an error), but any code that reads `task.done` from responses will fail.

**Before:**

```json
{
  "title": "Ship v2",
  "done": true
}
```

**After:**

```json
{
  "title": "Ship v2",
  "completed": true
}
```

```python
# Before
if task["done"]:
    print("Task finished!")

# After
if task["completed"]:
    print("Task finished!")
```

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP `422 Unprocessable Entity`.

**Before:**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After:**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

```python
# Before
resp = requests.post(
    "https://api.zrb.dev/tasks",
    json={"title": "New task title"}
)

# After
resp = requests.post(
    "https://api.zrb.dev/v2/tasks",
    headers={"Authorization": "Bearer abc123"},
    json={"title": "New task title", "project_id": "proj_abc123"}
)
```

You will need to determine the appropriate `project_id` for each task. Retrieve available projects via the projects API (see v2 docs).

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns a paginated envelope with `items`, `total`, and `next_cursor`. Code that directly iterates over the response array will break.

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
    {"id": "e5f67890-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```python
# Before — bare array
resp = requests.get("https://api.zrb.dev/tasks")
for task in resp.json():
    print(task["title"])

# After — paginated envelope
resp = requests.get("https://api.zrb.dev/v2/tasks")
data = resp.json()
for task in data["items"]:
    print(task["title"])

# To fetch the next page:
if data["next_cursor"]:
    resp = requests.get(
        "https://api.zrb.dev/v2/tasks",
        params={"cursor": data["next_cursor"]}
    )
```

You can control page size with the `limit` query parameter (default: 20).

---

## Migration Checklist

Use this checklist to track your migration progress:

- [ ] **Update base URL** — prepend `/v2/` to all endpoint paths
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change task ID type from integer to UUID string (DB schemas, type definitions, route parameters, tests)
- [ ] **Rename `done` to `completed`** — update all read and write paths: response parsing, conditional checks, and update request bodies
- [ ] **Add `project_id` to task creation** — supply `project_id` in every `POST /v2/tasks` request body; handle `422` errors for missing fields
- [ ] **Adapt list response parsing** — unwrap `items` from the paginated envelope; update iteration, total-count logic, and implement cursor-based pagination
- [ ] **Run integration tests** — verify against the v2 API, paying special attention to 401 (auth), 404 (old paths), and 422 (missing `project_id`) errors

---

## Upgrade

```bash
npm install zrb@2
```