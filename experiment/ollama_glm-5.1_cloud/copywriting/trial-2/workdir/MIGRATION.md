# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes require updates to your integration code. This guide walks through each one.

---

## 1. Endpoint paths now require `/v2/` prefix

All endpoints are now served under `/v2/`. Requests to the old paths (e.g. `GET /tasks`) will return 404.

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

If your code builds URLs dynamically, update the base path once:

```python
# Before
BASE_URL = "https://api.zrb.dev/tasks"

# After
BASE_URL = "https://api.zrb.dev/v2/tasks"
```

---

## 2. Authentication header changed

`X-Auth-Token` is no longer accepted. Requests using it receive HTTP 401. Use a standard `Authorization: Bearer` header instead.

**Before (v1):**
```http
X-Auth-Token: abc123yourapikey
```

**After (v2):**
```http
Authorization: Bearer abc123yourapikey
```

In code:

```python
# Before
headers = {"X-Auth-Token": API_KEY}

# After
headers = {"Authorization": f"Bearer {API_KEY}"}
```

---

## 3. Task `id` changed from integer to UUID string

Task IDs are now UUID strings instead of auto-incrementing integers. Any code that parses, stores, or compares IDs as integers must be updated.

**Before (v1):**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "..."}
```

**After (v2):**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
```

Update your data models and any path construction:

```python
# Before
task_id: int = response["id"]
url = f"/tasks/{task_id}"

# After
task_id: str = response["id"]
url = f"/v2/tasks/{task_id}"
```

If you store IDs in a database, change the column type from integer to `VARCHAR(36)` or a native UUID type.

---

## 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old name is not accepted in requests and is absent from responses.

**Before (v1):**
```json
{"id": 1, "title": "Ship v1", "done": true}
```

**After (v2):**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v1", "completed": true}
```

When updating a task:

```python
# Before
payload = {"done": True}

# After
payload = {"completed": True}
```

In client-side models:

```typescript
// Before
interface Task { id: number; title: string; done: boolean; created_at: string; }

// After
interface Task { id: string; title: string; completed: boolean; project_id: string; created_at: string; }
```

---

## 5. `project_id` is now required when creating tasks

Task creation (`POST /v2/tasks`) requires a `project_id` field. Omitting it returns HTTP 422.

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

In code:

```python
# Before
payload = {"title": task_title}

# After
payload = {"title": task_title, "project_id": project_id}
```

If you don't yet have a project concept, you'll need to create one (or use a default) before creating tasks. Check the v2 API docs for project creation endpoints.

---

## 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates the response directly must be updated.

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
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetching all tasks now requires cursor-based pagination:

```python
# Before (v1) — single request
tasks = requests.get(f"{BASE_URL}", headers=headers).json()

# After (v2) — paginate through all results
tasks = []
cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    page = requests.get(f"{BASE_URL}", headers=headers, params=params).json()
    tasks.extend(page["items"])
    cursor = page.get("next_cursor")
    if not cursor:
        break
```

Query parameters for list endpoints:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cursor` | Pagination cursor from a previous response | — |
| `limit` | Max results per page | 20 |

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all endpoint paths
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`
- [ ] **Update ID handling** — change task `id` from `int` to `str` (UUID); update database columns, type annotations, and path templates
- [ ] **Rename `done` → `completed`** — update request payloads, response parsers, and model definitions
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` includes a `project_id`; handle HTTP 422 if missing
- [ ] **Parse paginated envelope** — update list-response parsing from bare array to `{items, total, next_cursor}`; implement cursor pagination loops
- [ ] **Run integration tests** — exercise all five endpoints against a v2 staging environment
- [ ] **Update API client library** — if you maintain a wrapper, release a major version bump alongside this migration

---

Upgrade now:

```bash
pip install --upgrade zrb
```