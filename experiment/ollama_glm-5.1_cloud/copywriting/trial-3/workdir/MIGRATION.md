# Migrating from Zrb CLI v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and shows exactly what to update.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every URL path gains a `/v2/` prefix. Requests to the old paths will 404.

**Before (v1):**
```bash
curl https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl https://api.zrb.dev/v2/tasks
```

This applies to all endpoints: `/v2/tasks`, `/v2/tasks/{id}`, etc.

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: abc123" https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer abc123" https://api.zrb.dev/v2/tasks
```

---

### 3. Task `id` changed from integer to UUID string

Task IDs are now UUIDs, not integers. Any code that parses, stores, or validates IDs as integers must be updated.

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

Implications:
- Database columns storing IDs must change from `INTEGER` to `VARCHAR`/`TEXT` (36+ characters).
- URL path parameters in route definitions must accept strings instead of integers.
- Any equality or lookup logic that casts IDs to `int` must be updated.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now called `completed`. The old name is not accepted in requests and is absent from responses.

**Before (v1) — read response:**
```json
{"id": 1, "title": "Buy milk", "done": false, "created_at": "..."}
```

**After (v2) — read response:**
```json
{"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
```

**Before (v1) — update request:**
```json
{"done": true}
```

**After (v2) — update request:**
```json
{"completed": true}
```

A global find-and-replace of `"done"` → `"completed"` in your API client code will catch most cases, but be careful not to rename unrelated uses of `done`.

---

### 5. Task creation now requires `project_id`

The `POST /v2/tasks` endpoint requires a `project_id` field. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

If you don't yet have a project ID, you'll need to create a project first (see the v2 Projects API docs) before creating tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

List endpoints no longer return a bare JSON array. They now return an envelope object with `items`, `total`, and `next_cursor`.

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
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Implications:
- Code that iterates directly over the response array must now iterate over `response.items` (or `response["items"]`).
- To fetch all results, you must paginate: when `next_cursor` is present, pass `?cursor=<next_cursor>` on the next request.
- A `limit` query parameter is now supported (default: 20).
- The `total` field gives the overall count across all pages.

**Before (v1) — fetch all tasks (assumed single page):**
```python
import requests

resp = requests.get("https://api.zrb.dev/tasks", headers={"X-Auth-Token": "abc123"})
tasks = resp.json()
for task in tasks:
    print(task["title"])
```

**After (v2) — fetch all tasks with pagination:**
```python
import requests

base_url = "https://api.zrb.dev/v2/tasks"
headers = {"Authorization": "Bearer abc123"}
cursor = None

while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    resp = requests.get(base_url, headers=headers, params=params)
    data = resp.json()
    for task in data["items"]:
        print(task["title"])
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

- [ ] **Update all endpoint URLs** — add `/v2/` prefix to every API path.
- [ ] **Switch authentication header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Update ID handling** — change ID type from integer to UUID string in models, databases, route params, and validation logic.
- [ ] **Rename `done` to `completed`** — update all request bodies, response parsers, and model fields.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes `project_id`; create projects first if needed.
- [ ] **Update list-response parsing** — unwrap the paginated envelope (`response["items"]` instead of `response`).
- [ ] **Implement cursor-based pagination** — loop on `next_cursor` to fetch all results; update any code that assumed a single-page response.
- [ ] **Test error handling** — verify your code handles 401 (old auth header) and 422 (missing `project_id`) gracefully.
- [ ] **Remove v1 fallback logic** — once migration is complete, clean up any v1 compatibility shims.

---

## Upgrade

```bash
npm install -g zrb@2
```