# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These changes break every v1 integration. This guide covers each breaking change with before/after examples and a migration checklist.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every URL path gains a `/v2/` prefix. Requests to the old paths will return `404`.

**Before (v1):**

```bash
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```bash
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Before (v1, in code):**

```python
BASE_URL = "https://api.zrb.io/tasks"
```

**After (v2, in code):**

```python
BASE_URL = "https://api.zrb.io/v2/tasks"
```

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

v2 drops the custom `X-Auth-Token` header. Requests using the old header receive `HTTP 401 Unauthorized`.

**Before (v1):**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.io/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.io/v2/tasks
```

**Before (v1, in code):**

```python
headers = {"X-Auth-Token": api_key}
```

**After (v2, in code):**

```python
headers = {"Authorization": f"Bearer {api_token}"}
```

### 3. Task `id` changed from integer to UUID string

The `id` field is now a UUID string (`"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`) instead of an integer (`42`). Any code that parses, stores, or validates task IDs as integers will break.

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

**Before (v1, in code):**

```python
task_id = response["id"]  # int
url = f"https://api.zrb.io/tasks/{task_id}"
```

**After (v2, in code):**

```python
task_id = response["id"]  # UUID string
url = f"https://api.zrb.io/v2/tasks/{task_id}"
```

Update database columns, path parameters, and any type checks from integer to string/UUID.

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored; reading `done` from a response returns `undefined`/missing.

**Before (v1):**

```json
{
  "title": "Write tests",
  "done": false
}
```

**After (v2):**

```json
{
  "title": "Write tests",
  "completed": false
}
```

**Before (v1, in code):**

```python
if task["done"]:
    mark_complete()

# Updating a task:
payload = {"done": True}
```

**After (v2, in code):**

```python
if task["completed"]:
    mark_complete()

# Updating a task:
payload = {"completed": True}
```

Search your codebase for all reads and writes of the `done` field and replace with `completed`.

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns `HTTP 422 Unprocessable Entity`.

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

**Before (v1, in code):**

```python
payload = {"title": "New task title"}
response = requests.post(url, json=payload, headers=headers)
```

**After (v2, in code):**

```python
payload = {"title": "New task title", "project_id": "proj_abc123"}
response = requests.post(url, json=payload, headers=headers)
```

Determine which project each task belongs to and supply the correct `project_id` at creation time.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare `[]`. It returns an envelope with `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages.

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
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Before (v1, in code):**

```python
tasks = requests.get(url, headers=headers).json()
for task in tasks:
    print(task["title"])
```

**After (v2, in code):**

```python
def get_all_tasks():
    url = "https://api.zrb.io/v2/tasks"
    while url:
        data = requests.get(url, headers=headers).json()
        for task in data["items"]:
            yield task
        if data.get("next_cursor"):
            url = f"https://api.zrb.io/v2/tasks?cursor={data['next_cursor']}"
        else:
            url = None

for task in get_all_tasks():
    print(task["title"])
```

Any code that iterates the response directly as an array must be updated to unpack `response["items"]`, and any code that assumes all results arrive in one request must handle pagination.

---

## Migration Checklist

1. **Update base URL** — Add the `/v2/` prefix to all endpoint URLs.
2. **Switch auth header** — Replace `X-Auth-Token` with `Authorization: Bearer`. Remove all references to `X-Auth-Token`.
3. **Change ID type** — Update every place that stores, validates, or serializes task IDs from `integer` to `UUID string`. This includes database schemas, URL path parameters, and client-side type definitions.
4. **Rename `done` to `completed`** — Find all reads and writes of `done` in request bodies, response handlers, conditionals, and UI labels. Replace with `completed`.
5. **Add `project_id` to task creation** — Ensure every `POST /v2/tasks` request includes a `project_id`. Decide which project each task belongs to before migrating.
6. **Handle paginated list responses** — Update list handlers to unpack the envelope (`items`, `total`, `next_cursor`). Add cursor-based pagination logic where your integration previously assumed all results arrive in a single response.
7. **Test end-to-end** — Verify create, read, update, delete, and list operations against a v2 staging environment.

---

```
npm install zrb@2
```