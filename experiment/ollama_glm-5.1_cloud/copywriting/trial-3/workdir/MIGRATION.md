# Zrb Task API — Migrating from v1 to v2

This guide covers every breaking change between Zrb Task API v1 and v2. If you are currently using v1, follow the sections below to update your integration.

## Breaking Changes

### 1. Endpoint paths are now prefixed with `/v2/`

All v1 endpoints moved under the `/v2/` prefix. Requests to the old paths will receive `404 Not Found`.

```http
# Before (v1)
GET /tasks

# After (v2)
GET /v2/tasks
```

```http
# Before (v1)
POST /tasks

# After (v2)
POST /v2/tasks
```

This applies to every endpoint: `/tasks`, `/tasks/{id}` (GET, PUT, DELETE) all become `/v2/tasks`, `/v2/tasks/{id}`.

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive `401 Unauthorized`. Use the standard `Authorization` header with a `Bearer` scheme instead.

```http
# Before (v1)
X-Auth-Token: <your_api_key>

# After (v2)
Authorization: Bearer <your_api_token>
```

```python
# Before (v1)
headers = {"X-Auth-Token": api_key}

# After (v2)
headers = {"Authorization": f"Bearer {api_key}"}
```

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUIDs rather than auto-incrementing integers. Any code that parses, stores, or validates `id` as an integer must be updated.

```json
// Before (v1)
{
  "id": 42
}

// After (v2)
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

```python
# Before (v1) — integer lookup
task_id = 42
response = requests.get(f"/tasks/{task_id}")

# After (v2) — UUID string lookup
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
response = requests.get(f"/v2/tasks/{task_id}")
```

If your database or schema columns store `id` as an integer type, migrate them to a string/UUID type before switching to v2.

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. Any code that reads or writes this field must use the new name.

```json
// Before (v1)
{
  "done": false
}

// After (v2)
{
  "completed": false
}
```

```python
# Before (v1)
if task["done"]:
    print("Task finished")

# After (v2)
if task["completed"]:
    print("Task finished")
```

This also affects update requests:

```json
// Before (v1) — updating a task
{
  "done": true
}

// After (v2) — updating a task
{
  "completed": true
}
```

Sending `done` in a v2 request will be silently ignored, not treated as `completed`.

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

```json
// Before (v1)
{
  "title": "Write tests"
}

// After (v2)
{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

```python
# Before (v1)
task = requests.post("/tasks", json={"title": "Write tests"})

# After (v2)
task = requests.post(
    "/v2/tasks",
    json={"title": "Write tests", "project_id": "proj_abc123"},
)
```

If your integration creates tasks without a project context, you will need to assign them to an existing project or create a default project first.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. The response is now an object with `items`, `total`, and `next_cursor` fields.

```json
// Before (v1)
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```json
// After (v2)
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```python
# Before (v1) — direct array
tasks = requests.get("/tasks").json()
for task in tasks:
    print(task["title"])

# After (v2) — paginated envelope
data = requests.get("/v2/tasks").json()
for task in data["items"]:
    print(task["title"])

# Fetch the next page
if data["next_cursor"]:
    next_page = requests.get(f"/v2/tasks?cursor={data['next_cursor']}").json()
```

Any code that assumes the response is an array (e.g., iterating directly over the response, checking `response.length`) must be updated to unwrap `items` first.

## Migration Checklist

Work through these steps in order. Each step corresponds to a breaking change above.

- [ ] **Update all endpoint paths** — add the `/v2/` prefix to every request URL (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).
- [ ] **Switch the auth header** — replace `X-Auth-Token` with `Authorization: Bearer` in all requests and HTTP client configuration.
- [ ] **Migrate `id` handling** — change any integer-typed columns, variables, or validators to accept UUID strings. Update path construction and lookups.
- [ ] **Rename `done` to `completed`** — find every reference to the `done` field (read, write, serialization, display) and replace it with `completed`.
- [ ] **Add `project_id` to task creation** — include `project_id` in all `POST /v2/tasks` request bodies. Set up a default project if your integration lacks one.
- [ ] **Unwrap paginated lists** — update all list-handling code to read from the `items` key. Implement cursor-based pagination using `next_cursor` where needed.

---

Upgrade now:

```
npm install zrb@2
```