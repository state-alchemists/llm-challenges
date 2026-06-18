# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to address, with before/after examples for each.

---

## Breaking Changes

### 1. Endpoint prefix: all routes moved under `/v2/`

Every endpoint path now starts with `/v2/`. Requests to the old paths will return 404.

```diff
- GET  /tasks
+ GET  /v2/tasks

- GET  /tasks/{id}
+ GET  /v2/tasks/{id}

- POST /tasks
+ POST /v2/tasks

- PUT  /tasks/{id}
+ PUT  /v2/tasks/{id}

- DELETE /tasks/{id}
+ DELETE /v2/tasks/{id}
```

### 2. Authentication header changed

The `X-Auth-Token` header is removed. Requests that include it receive HTTP 401, even if the token is valid. Use a standard `Authorization: Bearer` header instead.

**Before:**

```bash
curl -H "X-Auth-Token: abc123" https://api.example.com/tasks
```

**After:**

```bash
curl -H "Authorization: Bearer abc123" https://api.example.com/v2/tasks
```

### 3. Task `id` changed from integer to UUID string

The `id` field on task objects is now a UUID string instead of an auto-incrementing integer. Any code that parses, stores, or validates task IDs must accept strings in UUID format.

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

This also affects URL parameters when fetching, updating, or deleting a task:

```diff
- GET /tasks/42
+ GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Field `done` renamed to `completed`

The boolean field `done` on the task object is now called `completed`. This affects task responses, update request bodies, and any client-side code that reads or writes this field.

**Before:**

```python
# Creating/updating a task
payload = {"title": "Ship v2", "done": True}
```

**After:**

```python
payload = {"title": "Ship v2", "completed": True}
```

**Before:**

```python
# Reading a task
if task["done"]:
    print("Task complete")
```

**After:**

```python
if task["completed"]:
    print("Task complete")
```

### 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns HTTP 422. You must first have a project to associate the task with.

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

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope object containing `items`, `total`, and `next_cursor`. Clients that expect a top-level array will break.

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

Fetch the next page by passing the cursor as a query parameter:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v2/tasks?cursor=cursor_xyz&limit=20"
```

Clients that previously iterated over the response array directly must now extract the `items` key first:

**Before:**

```python
tasks = requests.get("/tasks", headers=headers).json()
for task in tasks:
    print(task["title"])
```

**After:**

```python
page = requests.get("/v2/tasks", headers=headers).json()
for task in page["items"]:
    print(task["title"])
```

To fetch all tasks across pages:

```python
all_tasks = []
cursor = None
while True:
    params = {"cursor": cursor} if cursor else {}
    page = requests.get("/v2/tasks", headers=headers, params=params).json()
    all_tasks.extend(page["items"])
    cursor = page.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

Work through these items in order. Each corresponds to a breaking change above.

- [ ] **Update all endpoint URLs** — add the `/v2/` prefix to every request path (`/tasks` → `/v2/tasks`, `/tasks/42` → `/v2/tasks/{uuid}`, etc.).
- [ ] **Switch auth header** — replace `X-Auth-Token: <key>` with `Authorization: Bearer <key>`. Remove any `X-Auth-Token` handling from request interceptors or middleware.
- [ ] **Update ID handling** — change task ID types from `int` to `str` in data models, database schemas, URL route patterns, and validation logic.
- [ ] **Rename `done` to `completed`** — update all references: response deserialization, update payloads, conditionals, and any serialized state.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request body includes `project_id`. Update forms, seed scripts, and tests accordingly.
- [ ] **Parse paginated envelope** — replace top-level array iteration with `page["items"]` access. Implement cursor-based pagination loops where you previously fetched once.

---

## Upgrade

```bash
pip install --upgrade zrb
```