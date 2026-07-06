# Migrating from Zrb CLI v1 to v2

This guide covers every breaking change between v1 and v2 of the Zrb Task API.
Each section includes the change, why it matters, and before/after examples.

---

## Breaking Changes

### 1. Endpoint Prefix — `/v2/`

All endpoints are now prefixed with `/v2/`. The old `/tasks` routes return 404.

**Before (v1):**

```
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header

The `X-Auth-Token` header has been replaced with the standard `Authorization: Bearer` scheme. Requests using `X-Auth-Token` receive HTTP 401.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

---

### 3. Task `id` Type — Integer to UUID

Task IDs are now UUID strings instead of auto-incrementing integers. Any code that assumes an integer type or performs arithmetic on IDs will break. Existing integer IDs from v1 are **not** carried forward to v2; you must migrate your reference data.

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

---

### 4. Field Rename — `done` → `completed`

The `done` boolean field is renamed to `completed` in all request and response payloads. Sending `done` in a v2 request body is silently ignored.

**Before (v1) — Create/Update request:**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required Field — `project_id`

Task creation now requires a `project_id` field. Omitting it returns HTTP 422. You must obtain or create a project before creating tasks.

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

---

### 6. List Response Envelope — Bare Array to Paginated Object

List endpoints no longer return a bare array. The response is now a paginated envelope with `items`, `total`, and `next_cursor`. Consumers that iterate directly over the response body (e.g. `response.data.forEach(...)`) will break — they must now access `response.data.items`.

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
    {"id": "c3d4...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

#### Pagination

Use the cursor-based pagination to fetch additional pages. The `next_cursor` value is `null` when there are no more results.

```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

| Parameter | Type   | Default | Description                         |
|-----------|--------|---------|-------------------------------------|
| `cursor`  | string | —       | Cursor from the previous response   |
| `limit`   | int    | 20      | Max items per page                  |

---

## Complete Example: Before and After

### v1 Client

```python
import requests

API_KEY = "your_api_key"
BASE = "https://api.zrb.dev"

# List tasks
resp = requests.get(f"{BASE}/tasks", headers={"X-Auth-Token": API_KEY})
for task in resp.json():
    print(task["id"], task["title"], task["done"])

# Create a task
resp = requests.post(f"{BASE}/tasks",
    headers={"X-Auth-Token": API_KEY},
    json={"title": "My task"})
task = resp.json()

# Update a task
requests.put(f"{BASE}/tasks/{task['id']}",
    headers={"X-Auth-Token": API_KEY},
    json={"done": True})
```

### v2 Client

```python
import requests

TOKEN = "your_api_token"
BASE = "https://api.zrb.dev/v2"

# List tasks
resp = requests.get(f"{BASE}/tasks", headers={"Authorization": f"Bearer {TOKEN}"})
data = resp.json()
for task in data["items"]:
    print(task["id"], task["title"], task["completed"])

# Create a task (project_id is required)
resp = requests.post(f"{BASE}/tasks",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"title": "My task", "project_id": "proj_abc123"})
task = resp.json()

# Update a task
requests.put(f"{BASE}/tasks/{task['id']}",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"completed": True})
```

---

## Migration Checklist

- [ ] Update all endpoint URLs to include the `/v2/` prefix
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>` in every request
- [ ] Migrate persisted v1 integer task IDs to the new v2 UUIDs (build a mapping or re-seed)
- [ ] Replace all references to the `done` field with `completed` in request bodies and response parsing
- [ ] Add `project_id` to every task creation call — obtain or create a project if one does not yet exist
- [ ] Update list response handlers to read `response.items` from the paginated envelope instead of treating the response as a bare array
- [ ] Rebuild any client-side type definitions, interfaces, or schemas to match the v2 Task object shape
- [ ] Remove any v1-only assumptions: integer IDs, old auth headers, bare-array list responses, the `done` field name

---

## Upgrade

```bash
pip install zrb-cli>=2.0.0
```
