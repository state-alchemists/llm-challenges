# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows exactly what changed and how to update your code.

---

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | URL prefix | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Done field name | `done` | `completed` |
| 5 | Create requires | title only | `title` + `project_id` |
| 6 | List response | bare array | paginated envelope |

---

## 1. URL Prefix

All endpoints now live under `/v2/`.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token.

**Before (v1)**
```http
X-Auth-Token: <your_api_key>
```

**After (v2)**
```http
Authorization: Bearer <your_api_token>
```

Requests sent with `X-Auth-Token` will now receive **HTTP 401**. Update your HTTP client configuration to use the `Authorization: Bearer` scheme.

---

## 3. Task `id` Type

Task IDs are now UUID strings instead of integers. This affects any code that stores, parses, or constructs task IDs.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

**Migration steps:**
- Update any database columns or cache keys that store task IDs from `int` to `string` / `UUID`
- Replace integer parsing (`parseInt(id, 10)`) with string or UUID validation
- Update route parameter types in your router/handler code

---

## 4. Field Renamed: `done` → `completed`

The `done` boolean is renamed to `completed`. This affects request bodies for **Update Task** and any code that reads this field from responses.

**Before (v1) — Update Task request body**
```json
{ "title": "Updated title", "done": true }
```

**After (v2) — Update Task request body**
```json
{ "title": "Updated title", "completed": true }
```

**Before (v1) — reading task state**
```javascript
if (task.done) { ... }
```

**After (v2) — reading task state**
```javascript
if (task.completed) { ... }
```

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1) — Create Task**
```json
{ "title": "New task title" }
```

**After (v2) — Create Task**
```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

If you are creating tasks without tracking which project they belong to, you will need to introduce that association in your application. A common pattern is to store a default project ID in your environment or config and include it on every create request.

---

## 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They now return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1) — List Tasks response**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — List Tasks response**
```json
{
  "items": [
    { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination usage:**
- To fetch the next page, pass `?cursor=<next_cursor>` on the same endpoint
- `next_cursor` is `null` when there are no more pages
- The `limit` query param controls page size (default: 20)

**Before (v1) — iterating all tasks**
```javascript
const tasks = await response.json();  // direct array
tasks.forEach(task => { ... });
```

**After (v2) — iterating all tasks**
```javascript
const { items: tasks, total, next_cursor } = await response.json();
tasks.forEach(task => { ... });
// fetch next page:
// const next = await fetch(`/v2/tasks?cursor=${next_cursor}`);
```

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID handling: integer → UUID string
- [ ] Rename all occurrences of `task.done` to `task.completed`
- [ ] Add `project_id` to every task creation request
- [ ] Update list response parsing: extract `items` from envelope, use `total` and `next_cursor` for pagination
- [ ] Update any database columns, cache keys, or serialization that stored `done` or integer task IDs
- [ ] Run your test suite against the v2 endpoint and fix any failures

---

## Upgrade Command

Once your codebase is updated, install v2:

```bash
npm install zrb-cli@latest
# or
pip install zrb-cli --upgrade
```
