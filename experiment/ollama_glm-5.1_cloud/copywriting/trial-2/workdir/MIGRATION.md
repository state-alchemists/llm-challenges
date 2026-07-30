# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change with before/after examples so you can update your integration quickly.

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

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

If your code builds URLs from a base path, add the prefix in one place:

```python
# v1
BASE = "https://api.zrb.dev"

# v2
BASE = "https://api.zrb.dev/v2"
```

---

## 2. Authentication Header

The `X-Auth-Token` header is removed. Requests using it will receive **HTTP 401**. Replace it with a standard `Authorization: Bearer` header.

**Before (v1):**

```bash
curl -H "X-Auth-Token: abc123" https://api.zrb.dev/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer abc123" https://api.zrb.dev/v2/tasks
```

```python
# v1
headers = {"X-Auth-Token": API_KEY}

# v2
headers = {"Authorization": f"Bearer {API_KEY}"}
```

---

## 3. Task IDs Are UUIDs

The `id` field changed from an integer to a UUID string. Any code that stores, compares, or serializes task IDs as integers will break.

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

```python
# v1 — integer ID
task_id: int = response["id"]

# v2 — UUID string
task_id: str = response["id"]
```

If you use task IDs in URL paths, query params, or database foreign keys, update those columns and route patterns from integer to string before migrating.

---

## 4. `done` Renamed to `completed`

The boolean field `done` is now `completed`. This affects both read (response objects) and write (update request bodies).

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

```python
# v1
is_done = task["done"]
payload = {"done": True}

# v2
is_done = task["completed"]
payload = {"completed": True}
```

A global find-and-replace of the key name (`done` → `completed`) in your API layer is usually sufficient. Watch for false positives if "done" appears in unrelated strings or comments.

---

## 5. `project_id` Is Required on Creation

Creating a task now requires a `project_id` field. Requests that omit it receive **HTTP 422**.

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

```bash
# v1
curl -X POST -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}' \
  https://api.zrb.dev/v2/tasks

# v2
curl -X POST -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}' \
  https://api.zrb.dev/v2/tasks
```

If your integration doesn't have a project concept yet, you'll need to create at least one project and pass its ID on every create call.

---

## 6. List Responses Use a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Code that iterates the top-level response as an array will break.

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

```python
# v1 — bare array
tasks = response.json()
for task in tasks:
    ...

# v2 — envelope
data = response.json()
for task in data["items"]:
    ...

# Pagination
if data.get("next_cursor"):
    next_url = f"/v2/tasks?cursor={data['next_cursor']}"
```

**Query params** (new):
- `cursor` — pass the `next_cursor` value to fetch the next page.
- `limit` — max results per page, default 20.

If you previously fetched all tasks in a single call, you must now loop over cursor pages until `next_cursor` is absent or `null`.

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2` prefix to all endpoint paths.
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove the old header; requests carrying it will be rejected with 401.
- [ ] **Update ID handling** — change task ID type from `int` to `str` (UUID) in models, databases, URL routes, and any serialization logic.
- [ ] **Rename `done` → `completed`** — update all reads of `task["done"]` and writes of `{"done": ...}` in request bodies.
- [ ] **Add `project_id` to create calls** — ensure every `POST /v2/tasks` request includes `project_id`. Handle the 422 error if it's missing.
- [ ] **Adapt list responses** — parse `items` from the envelope instead of treating the response as a bare array. Implement cursor-based pagination if you need to fetch all results.
- [ ] **Run integration tests** — verify all five endpoints against the v2 API before cutting over production traffic.

---

## Upgrade

```bash
npm install zrb-cli@2
```