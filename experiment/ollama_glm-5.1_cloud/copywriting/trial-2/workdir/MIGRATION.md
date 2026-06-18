# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to handle when upgrading from v1.

---

## Breaking Changes

### 1. Endpoint paths are now prefixed with `/v2/`

All endpoints moved under the `/v2/` prefix. Calls to the old paths will 404.

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

### 2. Authentication header changed

The `X-Auth-Token` header is no longer accepted. Requests using it receive HTTP 401. Replace it with a standard `Authorization: Bearer` header.

**Before (v1):**

```http
GET /tasks
X-Auth-Token: your_api_key
```

**After (v2):**

```http
GET /v2/tasks
Authorization: Bearer your_api_token
```

### 3. Task `id` changed from integer to UUID string

Task IDs are no longer auto-incremented integers. They are now UUID v4 strings.

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

**Impact:** Any code that stores, compares, or serializes task IDs as integers must be updated to handle UUID strings. URL path parameters for `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}` now expect a UUID.

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The `done` field is no longer returned in responses and is ignored in request bodies.

**Before (v1):**

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

**Impact:** Update all code that reads or writes the `done` field — including API clients, deserialization logic, and any client-side state management.

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP 422.

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

**Impact:** Every `POST /tasks` call must include `project_id`. If you don't have a project concept yet, you'll need to create one first (or use a default project ID provided by your team) before creating tasks.

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It now returns a paginated envelope object. Any code that expects a top-level array will break.

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
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination parameters:**

| Parameter | Description |
|-----------|-------------|
| `cursor` | Omit for the first page. Pass `next_cursor` from the previous response to fetch the next page. |
| `limit` | Max results per page. Default 20. |

**Impact:** Replace array iteration with extraction of the `items` key. To fetch all tasks across pages, loop while `next_cursor` is present:

```python
# v1 — single request, bare array
response = requests.get("/tasks", headers={"X-Auth-Token": api_key})
tasks = response.json()  # list

# v2 — paginated envelope
tasks = []
cursor = None
while True:
    params = {"limit": 100}
    if cursor:
        params["cursor"] = cursor
    response = requests.get(
        "/v2/tasks",
        params=params,
        headers={"Authorization": f"Bearer {api_token}"},
    )
    data = response.json()
    tasks.extend(data["items"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

Use this checklist to track your progress through the migration:

- [ ] **Update all endpoint paths** — add the `/v2/` prefix to every request URL (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).
- [ ] **Switch authentication header** — replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>`. Remove any `X-Auth-Token` references from HTTP clients, interceptors, and middleware.
- [ ] **Update task ID handling** — change any integer-based ID storage, validation, or comparison logic to accept UUID strings. Update URL routing and path parameter types.
- [ ] **Rename `done` to `completed`** — update all request bodies, response parsers, field access, and serialization that reference the `done` field.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a `project_id`. Set up a default project or project-creation flow if needed.
- [ ] **Handle paginated list responses** — replace array-based response parsing with envelope extraction (`response["items"]`). Implement cursor-based pagination for listing tasks.

---

## Upgrade

```bash
pip install --upgrade zrb
```