# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements come with six breaking changes that require code updates before switching. This guide covers each one with concrete before/after examples.

## Breaking Changes

### 1. Endpoint paths are now prefixed with `/v2/`

All task endpoints moved under the `/v2/` prefix. Requests to the old paths will receive `404`.

**Before (v1):**

```
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

Update your base URL or route configuration to include the `/v2/` prefix. If you use a client library that constructs URLs from a base path, change the base from `/` to `/v2/` (or from `/tasks` to `/v2/tasks`, depending on your abstraction).

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests that use it will receive `401 Unauthorized`.

**Before (v1):**

```python
import requests

resp = requests.get(
    "https://api.example.com/tasks",
    headers={"X-Auth-Token": "your_api_key"},
)
```

**After (v2):**

```python
import requests

resp = requests.get(
    "https://api.example.com/v2/tasks",
    headers={"Authorization": "Bearer your_api_token"},
)
```

If your HTTP client supports a built-in auth helper, prefer it:

```python
resp = requests.get(
    "https://api.example.com/v2/tasks",
    auth=("bearer", "your_api_token"),  # requests sends this as Authorization: Bearer
)
```

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of integers. Any code that casts `id` to an integer, relies on numeric ordering, or constructs URLs by interpolating an integer will break.

**Before (v1):**

```python
task = resp.json()
task_id = task["id"]          # 42
url = f"/tasks/{task_id}"     # /tasks/42
```

**After (v2):**

```python
task = resp.json()
task_id = task["id"]          # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
url = f"/v2/tasks/{task_id}"  # /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update any type annotations, database columns, or log formats that assume an integer `id`.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. Responses and request bodies that use `done` will be ignored or rejected.

**Before (v1):**

```python
# Reading a task
is_done = task["done"]

# Updating a task
resp = requests.put(
    f"https://api.example.com/tasks/{task_id}",
    json={"done": True},
)
```

**After (v2):**

```python
# Reading a task
is_completed = task["completed"]

# Updating a task
resp = requests.put(
    f"https://api.example.com/v2/tasks/{task_id}",
    json={"completed": True},
)
```

Do a project-wide search for the key `"done"` in task-related dictionaries and payloads and replace each occurrence with `"completed"`.

---

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**

```python
resp = requests.post(
    "https://api.example.com/tasks",
    json={"title": "Write tests"},
)
```

**After (v2):**

```python
resp = requests.post(
    "https://api.example.com/v2/tasks",
    json={
        "title": "Write tests",
        "project_id": "proj_abc123",
    },
)
```

You will need to know the project identifier before creating tasks. Retrieve available projects from your project management dashboard or the projects API, then include the correct `project_id` in every create call.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It now returns an envelope object containing `items`, `total`, and `next_cursor`. Code that iterates the top-level response as a list will break.

**Before (v1):**

```python
resp = requests.get("https://api.example.com/tasks")
tasks = resp.json()  # [...]
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
resp = requests.get("https://api.example.com/v2/tasks")
data = resp.json()   # {"items": [...], "total": 42, "next_cursor": "cursor_xyz"}
tasks = data["items"]
for task in tasks:
    print(task["title"])

# Fetch the next page
if data["next_cursor"]:
    resp = requests.get(
        "https://api.example.com/v2/tasks",
        params={"cursor": data["next_cursor"]},
    )
```

If you need all results at once, loop until `next_cursor` is `null`. The `limit` query parameter controls page size (default 20).

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all task endpoint paths.
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove any `X-Auth-Token` usage.
- [ ] **Update `id` handling** — change type annotations, casts, and URL templates from integer to UUID string.
- [ ] **Rename `done` to `completed`** — search for all occurrences of the `"done"` key in task payloads and update them.
- [ ] **Add `project_id` to create requests** — ensure every `POST /v2/tasks` call includes a `project_id` field.
- [ ] **Parse paginated envelope** — update list-response handling to read from the `items` key and implement cursor-based pagination if you need more than the first page.
- [ ] **Run integration tests** — verify all five endpoints (`GET` list, `GET` single, `POST`, `PUT`, `DELETE`) work against the v2 API.
- [ ] **Remove v1 fallback code** — once migration is complete, clean up any v1 compatibility shims.

## Upgrade

```bash
npm install zrb@2
```