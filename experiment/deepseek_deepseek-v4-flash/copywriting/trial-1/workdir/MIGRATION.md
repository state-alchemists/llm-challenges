# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, paginated list endpoints, and stricter authentication.
Every existing integration needs updates — there is no backward-compatible mode.
This guide covers every breaking change with before/after examples.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoints prefixed with `/v2/` | All URL strings must change |
| 2 | `X-Auth-Token` header replaced by `Authorization: Bearer` | Auth code in every client must change |
| 3 | Task `id` changed from integer to UUID string | ID lookups, storage, and type handling break |
| 4 | Field `done` renamed to `completed` | Every read/write of task state breaks |
| 5 | `project_id` required on task creation | Create-task calls will fail with HTTP 422 |
| 6 | List responses wrapped in a paginated envelope | Array indexing and iteration logic breaks |

---

## 1. Endpoint Prefix

All endpoints now live under `/v2/`.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
```

The old paths return HTTP 404. Update your base URL or route prefix in every client.

---

## 2. Authentication Header

The authentication mechanism changed from a custom header to the standard Bearer scheme.

**Before (v1):**
```
X-Auth-Token: sk-abc123
```

**After (v2):**
```
Authorization: Bearer sk-abc123
```

Requests using `X-Auth-Token` receive HTTP 401 with no body. Update all client auth setup — both the header name and the value format (the `Bearer ` prefix is required). A token issued for v1 still works; only the transport changed.

---

## 3. Task ID Type

Task identifiers are now UUID strings, not integers.

**Before (v1):**
```json
{
  "id": 42
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

This affects every endpoint that references a task by ID. Code that formats IDs into URLs must stop casting to `int`:

```javascript
// Before (v1)
fetch(`/tasks/${taskId}`)           // taskId was a number

// After (v2)
fetch(`/v2/tasks/${taskId}`)        // taskId is now a string
```

Existing integer IDs are **not** preserved — v2 generates fresh UUIDs. If you stored task IDs in external systems, you must re-sync.

---

## 4. `done` → `completed`

The boolean field that marks task state has been renamed.

**Before (v1):**
```json
{
  "title": "Write tests",
  "done": false
}
```

**After (v2):**
```json
{
  "title": "Write tests",
  "completed": false
}
```

The v2 API ignores the `done` key. On reads, only `completed` is returned. On writes, the field is required (all fields on the Update endpoint remain optional, but the correct name is `completed`).

Scan your codebase for every reference to `task.done`, `task["done"]`, or equivalent:

```python
# Before (v1)
if task["done"]:
    print("Task is complete")

# After (v2)
if task["completed"]:
    print("Task is complete")
```

---

## 5. `project_id` Required on Creation

Every task now belongs to a project. The `project_id` field is required when creating a task.

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

Omitting `project_id` returns HTTP 422 with a validation error. You'll need a project identifier before you can create tasks — list available projects via `GET /v2/projects` (see project endpoint docs) or use the project ID from your configuration.

---

## 6. Paginated List Responses

List endpoints no longer return a bare array. The response is now a paginated envelope with cursors.

**Before (v1):**
```json
GET /tasks
→ [
    {"id": 1, "title": "Buy milk", "done": false, ...},
    {"id": 2, "title": "Ship v1", "done": true, ...}
  ]
```

**After (v2):**
```json
GET /v2/tasks
→ {
    "items": [
      {"id": "a1b2...", "title": "Buy milk", "completed": false, ...},
      {"id": "c3d4...", "title": "Ship v1", "completed": true, ...}
    ],
    "total": 42,
    "next_cursor": "cursor_xyz"
  }
```

Code that indexes the response directly must now read `.items`:

```javascript
// Before (v1)
const tasks = await response.json();
tasks.forEach(t => console.log(t.title));

// After (v2)
const body = await response.json();
body.items.forEach(t => console.log(t.title));
```

**Pagination:** use `?cursor=<next_cursor>` to fetch the next page. Use `?limit=N` (default 20) to control page size. When `next_cursor` is `null`, there are no more pages.

---

## Migration Checklist

- [ ] **1. Update endpoint paths** — add `/v2/` prefix to every API call.
- [ ] **2. Change auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **3. Update ID handling** — stop treating task IDs as integers; compare IDs as strings instead.
- [ ] **4. Rename `done` → `completed`** — update all client code that reads or writes the task state field.
- [ ] **5. Add `project_id` to task creation** — determine your project ID and include it in every `POST /v2/tasks` body.
- [ ] **6. Unwrap list responses** — read `response.items` instead of the response directly; add pagination loop logic if you fetch more than one page.
- [ ] **7. Re-sync external ID references** — if you stored integer task IDs in a database, cache, or third-party system, map them to the new UUIDs.
- [ ] **8. Regenerate API clients** — if you use an SDK or generated client, re-pull the v2 spec and regenerate.
- [ ] **9. Run integration tests** — exercise every endpoint type (list, get, create, update, delete) against v2 before deploying.

---

## Upgrade Command

```bash
pip install --upgrade zrb
```

After upgrading, verify the new version:

```bash
zrb --version
# Should show v2.x.x
```
