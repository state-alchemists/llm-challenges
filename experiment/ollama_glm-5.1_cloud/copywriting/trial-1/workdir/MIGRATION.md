# Migrating from Zrb v1 to v2

This guide covers every breaking change between Zrb Task API v1 and v2. If you are currently using v1, follow the sections below to update your integration.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every v1 endpoint path now requires the `/v2/` prefix. Requests to the old paths will receive HTTP 404.

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

If you use a base URL variable, update it once:

**Before:**

```python
BASE_URL = "https://api.zrb.dev"
```

**After:**

```python
BASE_URL = "https://api.zrb.dev/v2"
```

### 2. Authentication header changed

v2 replaces the custom `X-Auth-Token` header with the standard `Authorization: Bearer` scheme. Requests using the old header receive HTTP 401.

**Before (v1):**

```python
headers = {"X-Auth-Token": api_key}
```

**After (v2):**

```python
headers = {"Authorization": f"Bearer {api_key}"}
```

**Before (v1) with curl:**

```bash
curl -H "X-Auth-Token: $API_KEY" https://api.zrb.dev/tasks
```

**After (v2) with curl:**

```bash
curl -H "Authorization: Bearer $API_KEY" https://api.zrb.dev/v2/tasks
```

### 3. Task `id` changed from integer to UUID string

v1 used auto-incrementing integers. v2 uses UUID strings. Any code that stores, compares, or validates task IDs must handle strings instead of integers.

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

If your database schema defines the ID column as an integer, migrate it to a string type (e.g., `VARCHAR(36)` in SQL, `String` in most ORMs).

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Sending `done` in a request body is silently ignored—use `completed` instead.

**Before (v1):**

```python
# Creating or updating a task
payload = {"title": "Ship release", "done": True}
response = requests.put(f"{BASE_URL}/tasks/42", json=payload, headers=headers)
```

**After (v2):**

```python
payload = {"title": "Ship release", "completed": True}
response = requests.put(f"{BASE_URL}/tasks/{task_id}", json=payload, headers=headers)
```

**Before (v1) — reading a task:**

```python
if task["done"]:
    print("Task is finished")
```

**After (v2) — reading a task:**

```python
if task["completed"]:
    print("Task is finished")
```

### 5. Task creation now requires `project_id`

v2 introduces projects. Every task must belong to a project, so `project_id` is a required field on `POST /v2/tasks`. Omitting it returns HTTP 422.

**Before (v1):**

```python
payload = {"title": "New task title"}
response = requests.post(f"{BASE_URL}/tasks", json=payload, headers=headers)
```

**After (v2):**

```python
payload = {"title": "New task title", "project_id": "proj_abc123"}
response = requests.post(f"{BASE_URL}/tasks", json=payload, headers=headers)
```

If you do not yet have a project ID, create one through the Projects API before creating tasks.

### 6. List endpoints return a paginated envelope instead of a bare array

v1 returned a bare JSON array. v2 wraps results in a paginated envelope containing `items`, `total`, and `next_cursor`.

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
    {"id": "e5f6-7890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Any code that iterates directly over the response array must now access the `items` key.

**Before (v1):**

```python
tasks = response.json()
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
data = response.json()
for task in data["items"]:
    print(task["title"])
```

To fetch the next page, pass the `next_cursor` value as a query parameter:

```python
next_cursor = data["next_cursor"]
if next_cursor:
    response = requests.get(
        f"{BASE_URL}/tasks?cursor={next_cursor}",
        headers=headers,
    )
```

You can also control page size with `?limit=N` (default 20).

---

## Migration Checklist

Use this step-by-step checklist to migrate your integration from v1 to v2.

- [ ] **Update base URL** — add `/v2/` prefix to all endpoint paths (or set a base URL that includes it).
- [ ] **Switch authentication header** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove any code that sets `X-Auth-Token`.
- [ ] **Update ID handling** — change task ID storage, validation, and serialization from integer to UUID string. Update database column types if applicable.
- [ ] **Rename `done` to `completed`** — update every read and write of the `done` field (request payloads, response parsing, conditionals, and type definitions).
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`. Set up project creation if you don't already have one.
- [ ] **Update list response parsing** — replace direct array iteration with `response["items"]` access. Implement cursor-based pagination using `next_cursor` and `?limit=` where needed.
- [ ] **Test all endpoints** — verify that list, get, create, update, and delete requests work with the new paths, headers, and shapes.
- [ ] **Update your upgrade command** — once ready, run:

```bash
npm install zrb@2
```