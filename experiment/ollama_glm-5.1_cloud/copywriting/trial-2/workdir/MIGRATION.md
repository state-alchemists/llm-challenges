# Migrating from Zrb Task API v1 to v2

v2 introduces projects, paginated list responses, and stricter authentication. The API surface has changed in six breaking ways — this guide walks through each one and provides a migration checklist at the end.

---

## Breaking Change 1 — Endpoint Prefix

All endpoints are now under `/v2/`. Requests to the old paths (e.g. `/tasks`) will return 404.

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

If you are constructing URLs from a base path, update the base:

```python
# v1
BASE_URL = "https://api.zrb.dev/tasks"

# v2
BASE_URL = "https://api.zrb.dev/v2/tasks"
```

---

## Breaking Change 2 — Authentication Header

The `X-Auth-Token` header is no longer accepted. v2 requires a `Bearer` token in the standard `Authorization` header. Requests using the old header receive **HTTP 401 Unauthorized**.

**Before (v1):**

```python
headers = {
    "X-Auth-Token": "sk_live_abc123",
}
requests.get("https://api.zrb.dev/tasks", headers=headers)
```

**After (v2):**

```python
headers = {
    "Authorization": "Bearer sk_live_abc123",
}
requests.get("https://api.zrb.dev/v2/tasks", headers=headers)
```

---

## Breaking Change 3 — Task `id` Is Now a UUID String

Task IDs changed from auto-assigned integers (`42`) to UUID strings (`"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`). Any code that stores, compares, or routes on task IDs must handle strings instead of integers.

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

If your database schema or models type `id` as an integer, migrate the column to a string/UUID type. URL path parameters also change accordingly (see Breaking Change 1).

---

## Breaking Change 4 — `done` Renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old key is absent from v2 responses and is not accepted in update requests.

**Before (v1):**

```python
# Creating/updating a task
payload = {"title": "Ship release", "done": True}

# Checking task state
if task["done"]:
    print("Task finished!")
```

**After (v2):**

```python
# Creating/updating a task
payload = {"title": "Ship release", "completed": True}

# Checking task state
if task["completed"]:
    print("Task finished!")
```

---

## Breaking Change 5 — `project_id` Is Required on Task Creation

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns **HTTP 422 Unprocessable Entity**. This field is absent in v1.

**Before (v1):**

```python
task = requests.post(
    "https://api.zrb.dev/tasks",
    json={"title": "New task title"},
    headers=headers,
)
```

**After (v2):**

```python
task = requests.post(
    "https://api.zrb.dev/v2/tasks",
    json={
        "title": "New task title",
        "project_id": "proj_abc123",
    },
    headers=headers,
)
```

Create a project (or look up an existing project ID) before creating tasks.

---

## Breaking Change 6 — List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. The response is now a JSON object with `items`, `total`, and `next_cursor` fields. Code that iterates the response array directly must access `response["items"]` instead and handle pagination.

**Before (v1):**

```python
resp = requests.get("https://api.zrb.dev/tasks", headers=headers)
for task in resp.json():
    print(task["title"])
```

**After (v2):**

```python
url = "https://api.zrb.dev/v2/tasks"
while url:
    resp = requests.get(url, headers=headers)
    data = resp.json()
    for task in data["items"]:
        print(task["title"])
    if data["next_cursor"]:
        url = f"https://api.zrb.dev/v2/tasks?cursor={data['next_cursor']}"
    else:
        url = None
```

The envelope also provides `total` for the overall count. Pass `?limit=N` to control page size (default 20).

---

## Migration Checklist

Use this step-by-step list to track your migration progress:

- [ ] **Prefix all endpoint URLs with `/v2/`** — update base URLs, route constants, and any hardcoded paths.
- [ ] **Switch auth header from `X-Auth-Token` to `Authorization: Bearer`** — remove the old header from all requests; verify that 401 errors go away.
- [ ] **Change `id` from integer to UUID string** — update database columns, model types, and any ID-based URL construction.
- [ ] **Rename `done` to `completed`** — search all code that reads or writes the `done` field and replace it (responses, requests, conditionals, tests).
- [ ] **Add `project_id` to every task creation call** — ensure a valid project ID is supplied; handle 422 errors for missing values.
- [ ] **Parse list responses from the paginated envelope** — replace direct array access with `response["items"]`; add cursor-based pagination where needed.
- [ ] **Run your test suite against the v2 API** — confirm all request/response shapes match the new spec.
- [ ] **Remove any v1 compatibility shims** — once fully migrated, clean up fallback code.

---

## Upgrade

```bash
pip install --upgrade zrb
```