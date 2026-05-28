# Migrating from Zrb v1 to v2

This guide covers every breaking change between the Zrb Task API v1 and v2. Each change includes a before/after example so you can update your code confidently.

**Audience:** Developers with existing v1 integrations. You do not need to know v2 to read this.

---

## Overview of Changes

| Area | v1 | v2 |
|---|---|---|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| Task `id` type | integer | UUID string |
| Task `done` field | `done` | `completed` |
| Create Task | `title` only | `title` + `project_id` |
| List response | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints have moved from bare paths to `/v2/`. Any request to `/tasks` will not reach the v2 API.

**Before (v1):**

```
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The authentication mechanism has changed from a custom header to the standard Bearer token scheme. Requests using the old header receive HTTP 401.

**Before (v1):**

```
X-Auth-Token: your_api_key
```

**After (v2):**

```
Authorization: Bearer your_api_token
```

---

## 3. Task ID: Integer → UUID String

Task identifiers are now UUID strings instead of auto-incrementing integers. All references to task IDs in URLs, stored references, and local state must be updated.

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

ID comparisons that relied on numeric ordering or `===` against integers will need to be reworked for string comparison.

---

## 4. Task Field: `done` Renamed to `completed`

The boolean field indicating task completion has been renamed. Code that reads, writes, or serialises task state must reference the new property name.

**Before (v1) — reading a task:**

```javascript
if (task.done) {
  markComplete(task.id);
}
```

**After (v2):**

```javascript
if (task.completed) {
  markComplete(task.id);
}
```

**Before (v1) — updating a task:**

```json
PUT /tasks/42
{
  "done": true
}
```

**After (v2):**

```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "completed": true
}
```

Using `done` in a v2 request body is silently ignored — it will not set the completion status.

---

## 5. Create Task Requires `project_id`

Creating a task now requires a `project_id` field. Supplying only `title` returns HTTP 422. You must obtain or create a project before creating tasks under it.

**Before (v1):**

```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2):**

```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration note:** If you do not have an existing project, use the Projects API (if available) or your Zrb dashboard to create one. `project_id` values are strings with a `proj_` prefix.

---

## 6. List Endpoints Return a Paginated Envelope

List responses are no longer bare arrays. They now return a paginated envelope with `items`, `total`, and `next_cursor`. Pagination is cursor-based; use the `cursor` and `limit` query parameters.

**Before (v1):**

```
GET /tasks
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1",  "done": true,  "created_at": "..."}
]
```

**After (v2):**

```
GET /v2/tasks?limit=20&cursor=cursor_xyz
```

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v2",  "completed": true,  "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_def"
}
```

To paginate, pass `?cursor=<next_cursor>` from the previous response. An absent or `null` `next_cursor` means there are no more pages.

**Before (v1) — consuming the list:**

```javascript
const tasks = await fetchJSON("/tasks");
tasks.forEach(t => renderTask(t));
```

**After (v2):**

```javascript
const { items, total, next_cursor } = await fetchJSON("/v2/tasks?limit=20");
items.forEach(t => renderTask(t));
// Use next_cursor to fetch the next page
```

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint URLs** — prepend `/v2` to all API path strings (e.g., `/tasks` → `/v2/tasks`).
- [ ] **Update auth headers** — replace `X-Auth-Token` with `Authorization: Bearer`. Obtain a token from your Zrb v2 dashboard if you have not already.
- [ ] **Audit task ID usage** — find every place your code stores, compares, or serialises task IDs. Expect UUID strings, not integers. Remove any code that assumes auto-incrementing numeric IDs.
- [ ] **Rename `done` to `completed`** — update all JSON payloads, state objects, and UI references. Searching for `"done"` in your codebase is a good start, but watch for destructured aliases too.
- [ ] **Add `project_id` to create-task calls** — identify every `POST /tasks` call and supply a `project_id` in the body. Create a project first if needed.
- [ ] **Update list-response consumers** — unwrap the paginated envelope. Read from `response.items` instead of the top-level array. Add cursor-based pagination logic if you fetch more than one page.
- [ ] **Run integration tests** — verify each endpoint with the new auth, new paths, and new payload shapes.
- [ ] **Remove v1 credential** — once confirmed on v2, revoke any old `X-Auth-Token` API keys.

---

## Upgrade

```bash
zrb upgrade
```

After upgrading, restart any services that depend on the Zrb API, update your client library, and run through the checklist above.
