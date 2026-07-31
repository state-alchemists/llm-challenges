# Migrating from Zrb Task API v1 to v2

This guide covers every breaking change between v1 and v2 of the Zrb Task API. If you are currently using v1, follow the sections below in order — each one describes a single breaking change, what it replaces, and how to update your code.

---

## 1. Endpoint paths now require the `/v2/` prefix

All v1 endpoints lived at the root path (`/tasks`). In v2, every endpoint is prefixed with `/v2/`. Requests to the old paths will return 404.

| v1                  | v2                     |
|---------------------|------------------------|
| `GET /tasks`        | `GET /v2/tasks`        |
| `GET /tasks/{id}`   | `GET /v2/tasks/{id}`   |
| `POST /tasks`       | `POST /v2/tasks`       |
| `PUT /tasks/{id}`   | `PUT /v2/tasks/{id}`   |
| `DELETE /tasks/{id}`| `DELETE /v2/tasks/{id}`|

**Before (v1):**

```python
import requests

resp = requests.get("https://api.zrb.dev/tasks")
```

**After (v2):**

```python
import requests

resp = requests.get("https://api.zrb.dev/v2/tasks")
```

---

## 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The custom `X-Auth-Token` header is no longer accepted. Sending it will return HTTP 401. Replace it with a standard `Authorization: Bearer <token>` header.

**Before (v1):**

```python
import requests

headers = {"X-Auth-Token": "my_api_key"}
resp = requests.get("https://api.zrb.dev/tasks", headers=headers)
```

**After (v2):**

```python
import requests

headers = {"Authorization": "Bearer my_api_token"}
resp = requests.get("https://api.zrb.dev/v2/tasks", headers=headers)
```

---

## 3. Task `id` changed from integer to UUID string

Task identifiers are now UUIDs instead of auto-incrementing integers. Any code that stores, compares, or serializes `id` as an integer must be updated to handle strings.

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

**Before (v1) — fetching a task by ID:**

```python
task_id = 42
resp = requests.get(f"https://api.zrb.dev/tasks/{task_id}", headers=headers)
```

**After (v2) — fetching a task by ID:**

```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
resp = requests.get(f"https://api.zrb.dev/v2/tasks/{task_id}", headers=headers)
```

---

## 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The semantics are unchanged — it still indicates whether the task is finished — but any code that reads, writes, or maps this field must use the new name.

**Before (v1) — creating/updating with `done`:**

```python
payload = {"title": "Ship v2", "done": True}
resp = requests.put("https://api.zrb.dev/tasks/42", json=payload, headers=headers)
```

**After (v2) — creating/updating with `completed`:**

```python
payload = {"title": "Ship v2", "completed": True}
resp = requests.put("https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", json=payload, headers=headers)
```

---

## 5. Task creation now requires `project_id`

Creating a task in v2 requires a `project_id` field. Omitting it returns HTTP 422. This means you must have a project identifier before you can create any tasks — obtain one from your project setup or admin console.

**Before (v1) — creating a task with just a title:**

```python
payload = {"title": "New task title"}
resp = requests.post("https://api.zrb.dev/tasks", json=payload, headers=headers)
```

**After (v2) — creating a task with a `project_id`:**

```python
payload = {"title": "New task title", "project_id": "proj_abc123"}
resp = requests.post("https://api.zrb.dev/v2/tasks", json=payload, headers=headers)
```

---

## 6. List endpoints return a paginated envelope instead of a bare array

`GET /tasks` in v1 returned a bare JSON array. In v2, `GET /v2/tasks` returns an object with `items`, `total`, and `next_cursor`. To iterate through all results, you must follow the cursor.

**Before (v1) — bare array response:**

```python
import requests

headers = {"X-Auth-Token": "my_api_key"}
resp = requests.get("https://api.zrb.dev/tasks", headers=headers)
tasks = resp.json()  # list[dict]
for task in tasks:
    print(task["id"], task["title"], task["done"])
```

**After (v2) — paginated envelope response:**

```python
import requests

headers = {"Authorization": "Bearer my_api_token"}
base_url = "https://api.zrb.dev/v2/tasks"
cursor = None

while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    resp = requests.get(base_url, headers=headers, params=params)
    data = resp.json()  # {"items": [...], "total": N, "next_cursor": "..." or None}
    for task in data["items"]:
        print(task["id"], task["title"], task["completed"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

The envelope also provides `total` (total number of matching tasks) and supports a `limit` query parameter (default 20) to control page size.

---

## Migration Checklist

Work through each item in order. After completing all steps, your integration should be fully compatible with v2.

- [ ] **Update all endpoint URLs** — add the `/v2/` prefix to every request path (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).
- [ ] **Replace the auth header** — change `X-Auth-Token: <key>` to `Authorization: Bearer <token>` in every request. Remove any `X-Auth-Token` references.
- [ ] **Update `id` handling** — change all code that treats task IDs as integers to treat them as UUID strings (parsing, storage, URL construction, equality checks).
- [ ] **Rename `done` to `completed`** — update all references: request bodies, response mappers, model classes, and any UI or logging that reads or writes the `done` field.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id` field. Provision project IDs if you don't have them yet.
- [ ] **Parse the paginated list envelope** — update all `GET /v2/tasks` consumers to read from `.items` instead of treating the response as a bare array. Implement cursor-based pagination where you need more than the first page of results.
- [ ] **Test the full request cycle** — send requests against the v2 API and verify that authentication, creation, listing, updating, and deletion all work with the new format.
- [ ] **Upgrade your client library** — run:

```bash
pip install --upgrade zrb
```