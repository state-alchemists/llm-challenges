# Migrating from Zrb CLI v1 to v2

This guide covers every breaking change between the v1 and v2 Task API. Read it in full before upgrading — several changes interact (e.g., endpoint path + response format + auth all shift at once).

## Overview of Changes

| Area | v1 | v2 |
|------|----|----|
| Base path | `/tasks` | `/v2/tasks` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| Task ID type | integer | UUID string |
| Completion field | `done` | `completed` |
| Task creation | `title` only | `title` + required `project_id` |
| List response | bare array | paginated envelope |

---

## Breaking Changes

### 1. Endpoint Prefix

All endpoints are now served under `/v2/`. Requests to the old paths receive an error.

**Before (v1):**

```http
GET /tasks
POST /tasks/{id}
```

**After (v2):**

```http
GET /v2/tasks
POST /v2/tasks/{id}
```

### 2. Authentication Header

The auth header has changed from a custom header to the standard Bearer scheme. The old `X-Auth-Token` header is rejected with HTTP 401.

**Before (v1):**

```http
X-Auth-Token: sk-abc123
```

**After (v2):**

```http
Authorization: Bearer sk-abc123
```

### 3. Task ID Type (integer → UUID)

Task IDs are now UUID strings instead of auto-incrementing integers. The `id` field in all responses and the path parameter for individual-task endpoints both change.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

```http
GET /tasks/42
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Impact:** Any code that stores, compares, or indexes tasks by their numeric ID must be updated to handle UUID strings. Foreign-key references in your own data store also need migration.

### 4. Field Rename: `done` → `completed`

The boolean completion field has been renamed from `done` to `completed`. This affects both request bodies (Create, Update) and response payloads.

**Before (v1):**

```json
{
  "title": "Write tests",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Write tests",
  "completed": true
}
```

**Impact:** Every read site and every write site that references the `done` key must be updated. The old key is silently ignored — it is not an alias.

### 5. Project ID Required on Task Creation

All tasks must now belong to a project. The `project_id` field is required when creating a task. Omitting it returns HTTP 422.

**Before (v1):**

```http
POST /tasks

{
  "title": "New task"
}
```

**After (v2):**

```http
POST /v2/tasks

{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

**Impact:** Your client must obtain or create a project ID before it can create tasks. Any v1 task-creation code that sends only a `title` will break immediately.

### 6. List Response Format (bare array → paginated envelope)

The list endpoint no longer returns a bare JSON array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

```python
# v1 — access the array directly
response = client.get("/tasks")
for task in response.json():
    print(task["title"])
```

**After (v2):**

```json
{
  "items": [
    {"id": "b2c3d4e5-...", "title": "Buy milk", "completed": false},
    {"id": "c3d4e5f6-...", "title": "Ship v2", "completed": true}
  ],
  "total": 2,
  "next_cursor": null
}
```

```python
# v2 — unwrap the envelope
response = client.get("/v2/tasks")
data = response.json()
for task in data["items"]:
    print(task["title"])
```

**Pagination:** Pass `?cursor=<next_cursor>` and `?limit=<N>` to fetch additional pages. The default page size is 20 items.

```http
GET /v2/tasks?cursor=cursor_xyz&limit=50
```

---

## Migration Checklist

Use this step-by-step checklist to update your codebase. Tick off each item as you go.

- [ ] **Update all endpoint paths** — replace every `/tasks` prefix with `/v2/tasks`.
- [ ] **Replace the auth header** — change `X-Auth-Token` to `Authorization: Bearer` (same token value).
- [ ] **Update Task ID handling** — change any code that parses, stores, or compares task IDs from integer to UUID string. Migrate foreign-key references in your data store.
- [ ] **Rename `done` to `completed`** — update every read (`task["done"]` → `task["completed"]`) and write (`{"done": true}` → `{"completed": true}`) across your client code.
- [ ] **Add `project_id` to Create Task calls** — ensure every `POST /v2/tasks` body includes a `project_id`. Get or create the project ID before making the call.
- [ ] **Unwrap the list response** — change list handlers to read from `data["items"]` instead of the raw array. Add cursor-based pagination if you need to fetch more than one page.
- [ ] **Test the migration** — run your integration suite against the v2 API. Verify that Create returns HTTP 201, auth failures return HTTP 401, and missing `project_id` returns HTTP 422.

---

## Upgrade Command

Install the latest Zrb CLI:

```bash
pip install --upgrade zrb
```
