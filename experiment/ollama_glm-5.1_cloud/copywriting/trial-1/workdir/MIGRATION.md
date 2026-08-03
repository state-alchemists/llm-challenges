# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and shows you exactly what to update.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every endpoint path gains a `/v2/` prefix. Requests to the old paths will receive `404`.

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

If your client builds URLs from a base path, update it:

```python
# Before
BASE_URL = "https://api.zrb.dev/tasks"

# After
BASE_URL = "https://api.zrb.dev/v2/tasks"
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it will receive `HTTP 401`.

**Before (v1):**

```python
headers = {
    "X-Auth-Token": "your_api_key"
}
```

**After (v2):**

```python
headers = {
    "Authorization": "Bearer your_api_token"
}
```

### 3. Task `id` type changed from integer to UUID string

Task IDs are now UUID strings instead of integers. Any code that parses, stores, or validates task IDs as integers will break.

**Before (v1):**

```json
{
  "id": 42
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

```python
# Before — integer lookup
task_id: int = response["id"]

# After — string lookup
task_id: str = response["id"]
```

If you use path-based routing or URL templates, update them:

```python
# Before
url = f"/tasks/{task_id}"       # task_id was int

# After
url = f"/v2/tasks/{task_id}"    # task_id is now a UUID string
```

Database schemas referencing task IDs as `INTEGER` must be migrated to `VARCHAR` or `UUID` columns.

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now called `completed`. Any code that reads or writes `done` will fail silently or throw a key error.

**Before (v1):**

```python
# Reading
if task["done"]:
    print("Task finished!")

# Writing
requests.put(url, json={"done": True})
```

**After (v2):**

```python
# Reading
if task["completed"]:
    print("Task finished!")

# Writing
requests.put(url, json={"completed": True})
```

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `HTTP 422`.

**Before (v1):**

```python
requests.post(
    "https://api.zrb.dev/tasks",
    headers=headers,
    json={"title": "New task title"}
)
```

**After (v2):**

```python
requests.post(
    "https://api.zrb.dev/v2/tasks",
    headers=headers,
    json={
        "title": "New task title",
        "project_id": "proj_abc123"
    }
)
```

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates the response directly as an array will break.

**Before (v1):**

```python
response = requests.get("https://api.zrb.dev/tasks", headers=headers)
tasks = response.json()  # bare array

for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
response = requests.get("https://api.zrb.dev/v2/tasks", headers=headers)
data = response.json()  # paginated envelope
tasks = data["items"]

for task in tasks:
    print(task["title"])

# Fetch next page
if data["next_cursor"]:
    response = requests.get(
        f"https://api.zrb.dev/v2/tasks?cursor={data['next_cursor']}",
        headers=headers
    )
```

The envelope structure:

```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Pass `?cursor=<next_cursor>` to fetch the next page. Use `?limit=N` (default 20) to control page size.

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all endpoints (e.g. `/tasks` → `/v2/tasks`).
- [ ] **Switch auth header** — replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>`. Remove any `X-Auth-Token` usage.
- [ ] **Migrate task ID storage** — change integer columns/fields to string/UUID. Update any ID validation, parsing, or formatting code.
- [ ] **Rename `done` to `completed`** — update all reads, writes, serializers, and conditionals that reference the `done` field.
- [ ] **Add `project_id` to task creation** — include `project_id` in every `POST /v2/tasks` request body.
- [ ] **Adapt list response handling** — parse `items` from the envelope instead of treating the response as a bare array. Implement cursor-based pagination where needed using `next_cursor` and `limit`.
- [ ] **Run integration tests** — verify all CRUD operations against the v2 API before switching production traffic.
- [ ] **Remove v1 fallback code** — once migration is complete, delete any compatibility shims targeting the old endpoints, headers, or field names.

---

## Upgrade

```bash
npm install zrb@2
```