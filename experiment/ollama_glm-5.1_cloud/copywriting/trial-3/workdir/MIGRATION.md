# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and shows exactly what to update.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every URL path gains the `/v2/` prefix. Calls to the old paths will return `404`.

**Before:**
```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After:**
```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**What to do:** Update your base URL or path constants. If you use a shared client, change the prefix in one place:

```python
# Before
BASE_URL = "https://api.zrb.dev/tasks"

# After
BASE_URL = "https://api.zrb.dev/v2/tasks"
```

---

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

v2 no longer accepts `X-Auth-Token`. Requests using the old header receive `401 Unauthorized`.

**Before:**
```http
GET /tasks
X-Auth-Token: abc123
```

**After:**
```http
GET /v2/tasks
Authorization: Bearer abc123
```

**Client library example:**

```python
# Before
headers = {"X-Auth-Token": api_key}

# After
headers = {"Authorization": f"Bearer {api_key}"}
```

If you use an HTTP client that supports auth helpers, switch to the built-in Bearer method:

```python
# Before
session.headers["X-Auth-Token"] = api_key

# After
session.headers["Authorization"] = f"Bearer {api_key}"
```

---

### 3. Task `id` type changed from integer to UUID string

Task IDs are no longer auto-incremented integers. They are now UUID strings.

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

**What to do:** Update any code that assumes `id` is an integer — type checks, path parameter formatting, database columns, or sort logic that relies on numeric ordering.

```python
# Before — will break
task_id: int = response["id"]
url = f"/tasks/{task_id}"

# After
task_id: str = response["id"]
url = f"/v2/tasks/{task_id}"
```

If you store task IDs in a database, alter the column type:

```sql
-- Before
-- id INTEGER PRIMARY KEY

-- After
-- id VARCHAR(36) PRIMARY KEY
```

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old name is no longer accepted in requests and no longer appears in responses.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Create/Update request:**

```python
# Before
payload = {"title": "Ship v2", "done": True}

# After
payload = {"title": "Ship v2", "completed": True}
```

**Response parsing:**

```python
# Before
if task["done"]:
    ...

# After
if task["completed"]:
    ...
```

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

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

**What to do:** Determine the project ID for each task before creating it. If you have a single project, set it as a constant. If you have multiple, add a project selector to your integration.

```python
# Before
task = client.create_task(title="New task title")

# After
task = client.create_task(title="New task title", project_id="proj_abc123")
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v2", "completed": true, "project_id": "proj_def456", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination:**

Pass `?cursor=<next_cursor>` to fetch the next page. Use `?limit=N` to control page size (default 20).

```
GET /v2/tasks?cursor=cursor_xyz&limit=50
```

**What to do:** Update response parsing. Code that iterated the response as an array must now iterate `response["items"]`. If you need all results, loop until `next_cursor` is `null` or absent.

```python
# Before
tasks = requests.get("/tasks", headers=headers).json()
for task in tasks:
    print(task["title"])

# After
url = "/v2/tasks"
while url:
    data = requests.get(url, headers=headers).json()
    for task in data["items"]:
        print(task["title"])
    cursor = data.get("next_cursor")
    url = f"/v2/tasks?cursor={cursor}" if cursor else None
```

---

## Migration Checklist

Work through these steps in order. Each step corresponds to a breaking change above.

- [ ] **1. Update endpoint paths** — add `/v2/` prefix to all API calls (or update the base URL in your client).
- [ ] **2. Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`. Remove any `X-Auth-Token` headers.
- [ ] **3. Update ID handling** — change task ID storage, comparisons, and type annotations from integer to UUID string.
- [ ] **4. Rename `done` → `completed`** — update request payloads, response parsers, conditionals, and any serialized fields.
- [ ] **5. Add `project_id` to task creation** — identify the correct project for each task and include `project_id` in every `POST /v2/tasks` call.
- [ ] **6. Handle paginated responses** — update list endpoints to parse the envelope (`items`, `total`, `next_cursor`) and implement cursor-based pagination.
- [ ] **7. Run integration tests** — verify all endpoints against a v2 staging environment before promoting to production.
- [ ] **8. Update your upgrade command** — see below.

---

## Upgrade

```bash
npm install zrb@2
```