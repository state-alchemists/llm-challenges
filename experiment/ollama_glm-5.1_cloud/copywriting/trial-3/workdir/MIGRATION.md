# Migrating from Zrb Task API v1 to v2

Zrb Task API v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements require changes to any client currently using v1.

This guide walks through every breaking change and shows the exact code updates needed.

---

## Breaking Changes

### 1. API endpoints are now prefixed with `/v2/`

All task endpoints moved from `/tasks` to `/v2/tasks`. Requests to the old paths will receive `404`.

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

In client code, update the base URL:

```diff
- base_url = "https://api.zrb.dev/tasks"
+ base_url = "https://api.zrb.dev/v2/tasks"
```

### 2. Authentication header changed

The `X-Auth-Token` header is no longer accepted. Use the standard `Authorization: Bearer` header instead. Requests with the old header receive `401 Unauthorized`.

**Before (v1):**

```http
X-Auth-Token: your_api_key
```

**After (v2):**

```http
Authorization: Bearer your_api_token
```

In client code:

```python
# v1
headers = {"X-Auth-Token": api_key}

# v2
headers = {"Authorization": f"Bearer {api_token}"}
```

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUIDs instead of auto-incrementing integers. Any code that parses, stores, or compares IDs as integers must be updated.

**Before (v1):**

```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2):**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

In client code, update any ID handling:

```python
# v1
task_id: int = response["id"]

# v2
task_id: str = response["id"]
```

Database columns or type annotations referencing integer IDs must also change:

```sql
-- v1
CREATE TABLE tasks (id INTEGER PRIMARY KEY, ...);

-- v2
CREATE TABLE tasks (id TEXT PRIMARY KEY, ...);
```

### 4. Field `done` renamed to `completed`

The boolean field `done` is now `completed`. This affects both read and write operations.

**Before (v1):**

```json
{"done": true}
```

**After (v2):**

```json
{"completed": true}
```

In client code:

```python
# v1 — reading
is_done = task["done"]

# v2 — reading
is_completed = task["completed"]

# v1 — updating
requests.put(url, json={"done": True})

# v2 — updating
requests.put(url, json={"completed": True})
```

### 5. `project_id` is now required when creating tasks

Creating a task now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**

```json
POST /tasks
{"title": "New task title"}
```

**After (v2):**

```json
POST /v2/tasks
{"title": "New task title", "project_id": "proj_abc123"}
```

In client code:

```python
# v1
requests.post(url, json={"title": "New task title"})

# v2
requests.post(url, json={"title": "New task title", "project_id": "proj_abc123"})
```

You must create or look up a project before you can create tasks. See the v2 Projects API documentation for details.

### 6. List endpoints return a paginated envelope

List responses are no longer bare arrays. They now return an envelope containing `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

In client code, update response parsing and iteration:

```python
# v1
tasks = response.json()  # list[dict]
for task in tasks:
    ...

# v2
data = response.json()  # dict
tasks = data["items"]
for task in tasks:
    ...

# To fetch all pages:
cursor = None
all_tasks = []
while True:
    params = {"cursor": cursor} if cursor else {}
    data = requests.get(url, params=params, headers=headers).json()
    all_tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

Pagination parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cursor`  | Opaque cursor from a previous response | — |
| `limit`   | Maximum results per page | 20 |

---

## Non-Breaking Additions

The following v2 features are additive and do not affect v1 clients after migration:

- **Projects** — tasks now belong to a project (required `project_id`).
- **Cursor pagination** — `?cursor=` and `?limit=` query parameters on list endpoints.

---

## Migration Checklist

Work through these items in order. Each step is independent, but the endpoint prefix change should come first since it affects all requests.

- [ ] **Update endpoint prefix** — prepend `/v2/` to all task endpoint URLs.
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Update ID handling** — change any integer ID parsing, storage, or comparison to use UUID strings.
- [ ] **Rename `done` to `completed`** — update reads, writes, and any client-side field references.
- [ ] **Add `project_id` to task creation** — include a valid `project_id` in all `POST /v2/tasks` request bodies.
- [ ] **Update list response parsing** — extract `items` from the paginated envelope instead of treating the response as a bare array.
- [ ] **Implement pagination** — consume `next_cursor` to fetch all results across pages.
- [ ] **Run integration tests** — verify all CRUD operations work against the v2 API.

---

## Upgrade

```bash
pip install --upgrade zrb
```