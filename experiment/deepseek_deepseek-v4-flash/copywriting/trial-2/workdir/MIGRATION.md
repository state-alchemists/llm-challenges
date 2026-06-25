# Zrb CLI — v1 to v2 Migration Guide

v2 introduces projects, UUID-based identifiers, cursor pagination, and stricter authentication. This guide covers every breaking change, with before-and-after examples, so you can upgrade your integration with minimal friction.

---

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Auth header: `X-Auth-Token` → `Authorization: Bearer` | All requests rejected with 401 |
| 2 | Endpoint prefix: `/tasks` → `/v2/tasks` | All URLs change |
| 3 | Task `id`: integer → UUID string | Client ID types, URL paths, local caches |
| 4 | Task field `done` → `completed` | Read/write model mismatch |
| 5 | Create Task requires `project_id` | Requests without one return 422 |
| 6 | List responses: bare array → paginated envelope | Response parsing breaks |
| 7 | Update Task body: `done` → `completed` | Update payloads silently ignored |

---

## 1. Authentication Header

`X-Auth-Token` is removed. All requests must use a Bearer token in the `Authorization` header. Requests with the old header receive HTTP 401.

**Before (v1):**

```
X-Auth-Token: sk-abc123
```

**After (v2):**

```
Authorization: Bearer sk-abc123
```

---

## 2. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

| Endpoint | v1 | v2 |
|----------|----|----|
| List Tasks | `GET /tasks` | `GET /v2/tasks` |
| Get Task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create Task | `POST /tasks` | `POST /v2/tasks` |
| Update Task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete Task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

Update your client's base path from `/tasks` to `/v2/tasks`.

---

## 3. Task `id`: Integer → UUID String

Task identifiers are now UUID v4 strings instead of auto-incrementing integers. This affects URL construction, local ID storage, and any code that treats `id` as a number.

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

**Client-side impact:**
- Replace any integer-based ID generation with the UUIDs the server returns.
- Remove assumptions about monotonic ordering of IDs.
- If you stored IDs as integers, migrate your local references to strings.

---

## 4. Task Field: `done` → `completed`

The boolean field indicating task completion is renamed from `done` to `completed`. The semantics are identical.

**Response parsing (v1):**

```javascript
const isDone = task.done;           // false
```

**Response parsing (v2):**

```javascript
const isDone = task.completed;      // false
```

---

## 5. Create Task Requires `project_id`

Creating a task now requires a `project_id` string in the request body. Omitting it returns HTTP 422. You must first create or obtain a project identifier.

**Before (v1):**

```javascript
// POST /tasks
fetch('/tasks', {
  method: 'POST',
  headers: { 'X-Auth-Token': 'sk-abc123' },
  body: JSON.stringify({ title: 'New task' })
});
```

**After (v2):**

```javascript
// POST /v2/tasks
fetch('/v2/tasks', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer sk-abc123' },
  body: JSON.stringify({
    title: 'New task',
    project_id: 'proj_abc123'
  })
});
```

---

## 6. List Responses: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`. All code that reads list responses must be updated.

**Before (v1) — bare array:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — paginated envelope:**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "c3d4...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Client-side impact:**

```javascript
// v1: direct array
const tasks = await response.json();
tasks.forEach(t => console.log(t.title));

// v2: paginated envelope
const body = await response.json();
const items = body.items;             // Task[]
const total = body.total;             // total matching records
const cursor = body.next_cursor;      // null if last page
items.forEach(t => console.log(t.title));
```

Use `?cursor=<cursor>` and `?limit=<n>` to paginate:

```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

Default limit is 20. A `null` or absent `next_cursor` means the last page.

---

## 7. Update Task: `done` → `completed`

The update request body must use `completed`, not `done`. Sending `done: true` will be ignored.

**Before (v1):**

```javascript
// PUT /tasks/42
fetch('/tasks/42', {
  method: 'PUT',
  headers: { 'X-Auth-Token': 'sk-abc123' },
  body: JSON.stringify({ done: true })
});
```

**After (v2):**

```javascript
// PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
fetch('/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890', {
  method: 'PUT',
  headers: { 'Authorization': 'Bearer sk-abc123' },
  body: JSON.stringify({ completed: true })
});
```

---

## Migration Checklist

Walk through these steps in order. Tick each one off before moving to the next.

- [ ] **Update authentication.** Replace every instance of the `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] **Update endpoint paths.** Add `/v2/` prefix to all task endpoints: `/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`, etc.
- [ ] **Obtain a `project_id`.** Create a project through the API or UI and store its identifier.
- [ ] **Update Create Task calls.** Add `project_id` to every `POST /v2/tasks` request body.
- [ ] **Update list response parsing.** Unwrap the paginated envelope: read `body.items` instead of the raw array. Handle `body.next_cursor` for pagination.
- [ ] **Rename `done` to `completed`.** Update all response parsing and all request bodies that reference task completion.
- [ ] **Update ID storage.** Change task ID type from integer to string. Remove any auto-increment or integer-based ID assumptions in your local database, caches, or client models.
- [ ] **Update `GET /v2/tasks/{id}` calls.** Pass UUID strings, not integers, in the URL path.
- [ ] **Test pagination.** Verify `?cursor=` and `?limit=` work with your client.
- [ ] **Verify error handling.** Ensure your client handles HTTP 401 (bad auth), 422 (missing `project_id`), and 404 (UUID not found) correctly.

---

## Upgrade Command

```bash
pip install --upgrade zrb-cli
```

After upgrading, run a full integration test against your staging environment before deploying to production.

---

> **Need help?** Open an issue at `github.com/state-alchemists/zrb-cli/issues` with a minimal reproduction of the problem.
