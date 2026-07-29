# Zrb Task API — Migrating from v1 to v2

This guide covers every breaking change between Zrb Task API v1 and v2, with before/after examples. If you are currently integrating against v1, follow this document end-to-end to update your client.

---

## Breaking Changes

### 1. Endpoint prefix: `/v2/` added to all routes

Every endpoint now lives under the `/v2/` prefix. Requests to the old paths will receive `404`.

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

**Migration tip:** Set a base URL constant in your client (e.g. `BASE_URL = "https://api.example.com/v2"`) so the prefix is managed in one place.

---

### 2. Authentication header: `X-Auth-Token` replaced by `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests that include it will receive `401 Unauthorized`.

**Before (v1):**

```python
import requests

resp = requests.get(
    "https://api.example.com/tasks",
    headers={"X-Auth-Token": "sk_abc123"},
)
```

**After (v2):**

```python
import requests

resp = requests.get(
    "https://api.example.com/v2/tasks",
    headers={"Authorization": "Bearer sk_abc123"},
)
```

**Migration tip:** If you use an HTTP client library that supports built-in bearer auth (e.g. `requests.Session`, `axios`), switch to its native auth mechanism rather than setting the header manually.

---

### 3. Task `id` type changed from integer to UUID string

Task IDs are now UUID strings instead of auto-incrementing integers. Any code that parses, stores, or validates IDs as integers will break.

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

**Migration tip:** Update your data model — change `id` columns from `INTEGER` to `VARCHAR(36)` (or `UUID` if your database supports it), and update any foreign-key references. Update URL construction from string interpolation of integers to direct string concatenation.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. Sending `done` in a request body is silently ignored; reading `done` from a response will return `undefined`/`null`.

**Before (v1):**

```python
# Creating/updating a task
task = requests.post(
    "https://api.example.com/tasks",
    json={"title": "New task"},
)
print(task.json()["done"])  # False

# Marking a task complete
requests.put(
    "https://api.example.com/tasks/42",
    json={"done": True},
)
```

**After (v2):**

```python
# Creating/updating a task
task = requests.post(
    "https://api.example.com/v2/tasks",
    json={"title": "New task", "project_id": "proj_abc123"},
)
print(task.json()["completed"])  # False

# Marking a task complete
requests.put(
    "https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    json={"completed": True},
)
```

**Migration tip:** Search your codebase for `done` in task-related contexts — response deserialization, conditional checks, request bodies, and database columns — and replace each with `completed`.

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` returns `422 Unprocessable Entity` if `project_id` is omitted. You must create or look up a project ID before creating tasks.

**Before (v1):**

```python
requests.post(
    "https://api.example.com/tasks",
    json={"title": "New task title"},
)
```

**After (v2):**

```python
requests.post(
    "https://api.example.com/v2/tasks",
    json={
        "title": "New task title",
        "project_id": "proj_abc123",
    },
)
```

**Migration tip:** If you have existing tasks without a project, contact your account admin to determine which project IDs to assign before migrating. For new integrations, create a project first, then pass its `project_id` on every task creation call.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. The response is now an object with `items`, `total`, and `next_cursor` fields. Code that iterates the top-level response as an array will break.

**Before (v1):**

```python
import requests

resp = requests.get(
    "https://api.example.com/tasks",
    headers={"X-Auth-Token": "sk_abc123"},
)
tasks = resp.json()  # list of task objects
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
import requests

base_url = "https://api.example.com/v2"
headers = {"Authorization": "Bearer sk_abc123"}

cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor

    resp = requests.get(f"{base_url}/tasks", headers=headers, params=params)
    data = resp.json()  # paginated envelope

    for task in data["items"]:
        print(task["title"])

    cursor = data.get("next_cursor")
    if not cursor:
        break
```

**Migration tip:** If you don't need pagination yet, you can unwrap the envelope with `tasks = resp.json()["items"]`. However, adding cursor-based pagination now will save you a second refactor when you need it.

---

## Migration Checklist

Work through these steps in order. Each step maps to one breaking change above.

- [ ] **1. Update all endpoint URLs** — add the `/v2/` prefix to every route your client calls. Consider centralizing the base URL.
- [ ] **2. Switch authentication header** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove any `X-Auth-Token` references.
- [ ] **3. Update ID handling** — change all task ID storage, comparison, and URL interpolation from integer to UUID string (`VARCHAR(36)` or native UUID type in your database).
- [ ] **4. Rename `done` → `completed`** — update every read, write, condition, and schema definition that references the `done` field.
- [ ] **5. Add `project_id` to task creation** — ensure all `POST /v2/tasks` requests include `project_id`. Resolve or create project IDs for existing tasks before migrating.
- [ ] **6. Update list-response parsing** — change all code that treats the list response as a bare array to read from the `items` key of the paginated envelope. Implement cursor-based pagination if desired.
- [ ] **7. Run integration tests** — point your test suite at the v2 sandbox and verify every endpoint.
- [ ] **8. Deploy** — once all tests pass, deploy your updated client.

---

## Upgrade

```bash
zrb upgrade --target v2
```