# Migrating from Zrb Task API v1 to v2

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and what you need to update in your integration.

---

## Breaking Changes

### 1. Endpoint prefix added

All endpoints are now under `/v2/`. Requests to the old paths (e.g. `GET /tasks`) will return 404.

**Before:**

```
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After:**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication header changed

The `X-Auth-Token` header is removed. Use a standard `Authorization: Bearer` header instead. Requests that still send `X-Auth-Token` will receive HTTP 401.

**Before:**

```python
headers = {
    "X-Auth-Token": "your_api_key"
}
```

**After:**

```python
headers = {
    "Authorization": "Bearer your_api_token"
}
```

### 3. Task `id` changed from integer to UUID string

The `id` field on every task object is now a UUID string, not an integer. Any code that references a task by ID, stores IDs, or parses IDs as numbers must be updated.

**Before:**

```python
task = client.get("/tasks/42")
task_id = task["id"]  # 42 (int)
```

**After:**

```python
task = client.get("/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
task_id = task["id"]  # "a1b2c3d4-e5f6-7890-abcd-ef1234567890" (str)
```

If your database or type definitions store task IDs as integers, migrate those columns to strings before switching to v2.

### 4. Task field `done` renamed to `completed`

The boolean field `done` on the task object is now called `completed`. Any code that reads or writes `done` must be updated.

**Before — reading a task:**

```python
if task["done"]:
    print("Task finished")
```

**After — reading a task:**

```python
if task["completed"]:
    print("Task finished")
```

**Before — updating a task:**

```python
client.put("/tasks/42", json={"done": True})
```

**After — updating a task:**

```python
client.put("/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", json={"completed": True})
```

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns HTTP 422.

**Before:**

```python
task = client.post("/tasks", json={
    "title": "Write tests"
})
```

**After:**

```python
task = client.post("/v2/tasks", json={
    "title": "Write tests",
    "project_id": "proj_abc123"
})
```

Create a project first (via the v2 Projects API) if you don't already have one.

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates directly over the response must access `response["items"]` instead.

**Before — listing tasks:**

```python
tasks = client.get("/tasks").json()
for task in tasks:
    print(task["title"])
```

**After — listing tasks (single page):**

```python
result = client.get("/v2/tasks", headers=headers).json()
for task in result["items"]:
    print(task["title"])
```

**After — paginating through all tasks:**

```python
tasks = []
cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    result = client.get("/v2/tasks", params=params, headers=headers).json()
    tasks.extend(result["items"])
    cursor = result.get("next_cursor")
    if not cursor:
        break
```

You can also pass `?limit=N` to control page size (default 20).

---

## Migration Checklist

1. **Update the base URL** — add `/v2/` prefix to every endpoint path.
2. **Switch authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
3. **Update ID handling** — change all task ID references from integers to UUID strings (URLs, database columns, type definitions).
4. **Rename `done` to `completed`** — update reads, writes, and any serialization/deserialization mappings.
5. **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
6. **Parse the paginated envelope** — unwrap `response["items"]` instead of iterating the response directly; implement cursor-based pagination where needed.
7. **Test against v2** — run your integration tests against the v2 API before switching production traffic.

---

## Upgrade

```bash
pip install --upgrade zrb
```