# Zrb Task API — v1 to v2 Migration Guide

Zrb CLI v2 introduces projects, stricter auth, paginated list endpoints, and several
backwards-incompatible changes. This guide maps every v1 pattern to its v2 equivalent.

v1 endpoints remain available for a deprecation window, but new features and fixes
land only on v2. Plan your migration before the v1 shutdown date (see deprecation notice
on your dashboard).

---

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Task field `done` | `"done": true` | `"completed": true` |
| 5 | Create Task body | `{ "title": "..." }` | `{ "title": "...", "project_id": "..." }` |
| 6 | List response format | bare array `[...]` | paginated envelope `{ items, total, next_cursor }` |

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**

```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

Requests to bare `/tasks` return HTTP 404 (no automatic redirect).

---

## 2. Authentication Header

The header name and value format have changed. v1's `X-Auth-Token` is no longer
accepted — requests using it will receive HTTP 401.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

Replace your API key with an API token generated from the dashboard. A migration
script is available at the end of this guide.

---

## 3. Task ID Type (integer → UUID)

Task IDs are now UUID strings instead of auto-incrementing integers. Any code that
stores, compares, or constructs task IDs must be updated.

**Before (v1) — integer IDs:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2) — UUID string IDs:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Impact:**

- URL construction: `GET /v2/tasks/${taskId}` continues to work, but `taskId` is now
  a string — ensure no implicit integer parsing (e.g. `parseInt(id, 10)`).
- Database columns storing task IDs should be migrated from `integer` to `uuid`.
- Comparisons and lookups that assumed numeric ordering no longer apply.
- Existing v1 integer IDs are **not reused**; v2 generates new UUIDs for each task.

---

## 4. Field Rename: `done` → `completed`

The boolean field `done` has been renamed to `completed`. The semantics are identical
— `false` means not done, `true` means done.

**Before (v1) — reading a task:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": true
}
```

**After (v2) — reading a task:**

```json
{
  "id": "a1b2c3d4-...",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123"
}
```

**Before (v1) — updating a task:**

```json
PUT /tasks/42
{
  "done": true
}
```

**After (v2) — updating a task:**

```json
PUT /v2/tasks/a1b2c3d4-...
{
  "completed": true
}
```

Sending `"done"` in a v2 request body will be silently ignored — it is not a valid
v2 field and will not be applied.

---

## 5. Create Task: `project_id` Now Required

v1 allowed creating a task with only a `title`. v2 requires a `project_id`. Omitting
it returns HTTP 422 with a validation error.

**Before (v1):**

```json
POST /tasks
{
  "title": "New task"
}
```

**After (v2):**

```json
POST /v2/tasks
{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

**How to migrate:**

1. Create a project via the new `POST /v2/projects` endpoint (see the v2 API
   reference) or use the default project ID shown on your dashboard.
2. Add `project_id` to every Create Task call in your codebase.

---

## 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare JSON array. They return a paginated envelope
with `items`, `total`, and `next_cursor`. Clients must unwrap `items` and handle
pagination to retrieve all results.

**Before (v1):**

```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2):**

```json
GET /v2/tasks
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123"},
    {"id": "c3d4...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination flow:**

```python
# v2 pagination example
cursor = None
while True:
    params = {"limit": 100}
    if cursor:
        params["cursor"] = cursor
    resp = requests.get("https://api.zrb.dev/v2/tasks", params=params, headers=headers)
    data = resp.json()
    for task in data["items"]:
        process(task)
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

**Changes to note:**
- Read `data["items"]` or `data['items']` — the array is now wrapped.
- Total count is available at `data["total"]` without fetching all pages.
- Default page size is 20; use `?limit=100` to increase (max 200).

---

## Migration Checklist

- [ ] **Update base URL.** Replace `/tasks` with `/v2/tasks` in all API calls.
- [ ] **Replace auth tokens.** Generate v2 API tokens from the dashboard. Update all
      clients to send `Authorization: Bearer <token>` instead of `X-Auth-Token`.
- [ ] **Handle UUID IDs.** Update any code that assumes integer IDs (type casts,
      arithmetic, numeric sorting, database schema).
- [ ] **Rename `done` to `completed`.** Update all reads and writes in your
      client code. Add a data migration if you store the field locally.
- [ ] **Add `project_id` to Create calls.** Create a project or retrieve the
      default, then pass it with every task creation.
- [ ] **Unwrap list responses.** Update list-response parsing to read
      `data.items` instead of iterating over the response directly. Add
      cursor-based pagination if you need more than one page.
- [ ] **Test a full write cycle.** Create, read, update, and delete a task in
      v2 end-to-end before deploying.

---

## Upgrade Command

Install the latest CLI and verify the version:

```bash
pip install --upgrade zrb-cli
zrb --version    # Should show v2.x.x
```
