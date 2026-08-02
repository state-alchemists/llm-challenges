# Zrb Task API — Migrating from v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change, with before/after examples for each.

---

## Breaking Changes

### 1. All endpoints are prefixed with `/v2/`

Every endpoint path now starts with `/v2/`. Requests to the old paths will receive `404`.

```diff
- GET /tasks
- GET /tasks/{id}
- POST /tasks
- PUT /tasks/{id}
- DELETE /tasks/{id}
+ GET /v2/tasks
+ GET /v2/tasks/{id}
+ POST /v2/tasks
+ PUT /v2/tasks/{id}
+ DELETE /v2/tasks/{id}
```

**Before:**
```http
GET /tasks HTTP/1.1
X-Auth-Token: my_key
```

**After:**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer my_token
```

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive `401 Unauthorized`.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

**Before (curl):**
```bash
curl -H "X-Auth-Token: $API_KEY" https://api.zrb.dev/tasks
```

**After (curl):**
```bash
curl -H "Authorization: Bearer $API_TOKEN" https://api.zrb.dev/v2/tasks
```

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Any code that stores, compares, or serializes task IDs as integers must be updated.

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

**Before (Python):**
```python
task_id: int = response["id"]
task = client.get(f"/tasks/{task_id}")
```

**After (Python):**
```python
task_id: str = response["id"]  # UUID string
task = client.get(f"/v2/tasks/{task_id}")
```

### 4. Task field `done` renamed to `completed`

The boolean field `done` on the task object is now called `completed`. Any code that reads or writes `done` must be updated.

**Before:**
```json
{
  "title": "Ship v1",
  "done": true
}
```

**After:**
```json
{
  "title": "Ship v1",
  "completed": true
}
```

**Before (JavaScript):**
```javascript
if (task.done) {
  console.log("Task finished");
}
```

**After (JavaScript):**
```javascript
if (task.completed) {
  console.log("Task finished");
}
```

**Before (update request):**
```json
PUT /tasks/42
{ "done": true }
```

**After (update request):**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{ "completed": true }
```

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before:**
```json
POST /tasks
{ "title": "New task title" }
```

**After:**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Before (curl):**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (curl):**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates the response directly as an array must navigate into `items`.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f67890-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`. Use `?limit=N` to control page size (default 20).

**Before (JavaScript):**
```javascript
const tasks = await response.json();
tasks.forEach(task => console.log(task.title));
```

**After (JavaScript):**
```javascript
const { items, next_cursor } = await response.json();
items.forEach(task => console.log(task.title));
if (next_cursor) {
  // fetch next page: GET /v2/tasks?cursor=<next_cursor>
}
```

**Before (Python, fetch all):**
```python
tasks = client.get("/tasks").json()
```

**After (Python, fetch all pages):**
```python
tasks = []
cursor = None
while True:
    url = "/v2/tasks"
    if cursor:
        url += f"?cursor={cursor}"
    page = client.get(url).json()
    tasks.extend(page["items"])
    cursor = page.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

Use this checklist to track your migration progress:

- [ ] **Update endpoint paths** — prefix all routes with `/v2/`
- [ ] **Update authentication** — replace `X-Auth-Token` header with `Authorization: Bearer`
- [ ] **Update task ID handling** — change ID storage, comparison, and serialization from integer to string (UUID)
- [ ] **Rename `done` to `completed`** — in both read and write paths (response parsing, update requests, conditionals)
- [ ] **Add `project_id` to task creation** — include `project_id` in all `POST /v2/tasks` request bodies
- [ ] **Update list-endpoint response handling** — unwrap the paginated envelope (`items` array, `total`, `next_cursor`) instead of treating the response as a bare array
- [ ] **Add pagination support** — implement cursor-based pagination where needed using `?cursor=` and `?limit=` query parameters
- [ ] **Run integration tests** against the v2 API to verify all changes

---

## Upgrade

```bash
npm install @zrb/sdk@2
```