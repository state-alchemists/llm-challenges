# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and what you need to update.

---

## Breaking Changes

### 1. Endpoint paths are now prefixed with `/v2/`

All task endpoints now live under the `/v2/` prefix. Requests to the old paths will 404.

**Before (v1):**

```
GET  /tasks
GET  /tasks/{id}
POST /tasks
PUT  /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET  /v2/tasks
GET  /v2/tasks/{id}
POST /v2/tasks
PUT  /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**What to do:** Update your base URL or route definitions. If you use a base URL config, change it once:

```js
// Before
const BASE = "https://api.zrb.dev";

// After
const BASE = "https://api.zrb.dev/v2";
```

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive **HTTP 401 Unauthorized**.

**Before (v1):**

```js
fetch("https://api.zrb.dev/tasks", {
  headers: { "X-Auth-Token": "sk_live_abc123" }
});
```

**After (v2):**

```js
fetch("https://api.zrb.dev/v2/tasks", {
  headers: { "Authorization": "Bearer sk_live_abc123" }
});
```

**What to do:** Replace the `X-Auth-Token` header with a standard `Authorization: Bearer` header everywhere you make authenticated requests.

---

### 3. Task `id` changed from integer to UUID string

Task IDs are no longer auto-incremented integers. They are now UUID strings.

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

**What to do:** If your code stores or compares task IDs as integers, change the type to string. URL path parameters referencing `{id}` now accept UUID strings, not numeric IDs.

```js
// Before
const taskUrl = `/tasks/${task.id}`;  // task.id === 42

// After
const taskUrl = `/v2/tasks/${task.id}`; // task.id === "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` has been renamed to `completed`. The old name is not accepted in request or response bodies.

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

**What to do:** Search your codebase for all references to the `done` field and replace with `completed`. This affects both request payloads and response consumers.

```js
// Before
if (task.done) { ... }

// After
if (task.completed) { ... }
```

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field in the request body. Omitting it returns **HTTP 422 Unprocessable Entity**.

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

**What to do:** Ensure every task creation call includes a valid `project_id`. If your integration doesn't have a concept of projects, you'll need to create at least one project and use its ID.

```js
// Before
const res = await fetch("/tasks", {
  method: "POST",
  body: JSON.stringify({ title: "New task" })
});

// After
const res = await fetch("/v2/tasks", {
  method: "POST",
  body: JSON.stringify({ title: "New task", project_id: projectId })
});
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`.

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

Fetch the next page by passing `?cursor=<next_cursor>`. Use `?limit=<n>` to control page size (default 20).

**What to do:** Update any code that treats the list response as a bare array. Access `items` for the task list, and implement cursor-based pagination if you need more than one page.

```js
// Before
const tasks = await response.json();  // direct array
tasks.forEach(task => { ... });

// After
const { items, total, next_cursor } = await response.json();
items.forEach(task => { ... });
if (next_cursor) {
  // fetch next page: GET /v2/tasks?cursor=<next_cursor>
}
```

---

## Migration Checklist

1. **Update base URL** — add `/v2/` prefix to all endpoint paths.
2. **Replace auth header** — swap `X-Auth-Token: <key>` for `Authorization: Bearer <key>` in all clients and SDK configurations.
3. **Change task ID handling** — update type annotations, DB columns, and comparisons from integer to UUID string.
4. **Rename `done` → `completed`** — search and replace all references in request bodies, response parsers, conditionals, and mappings.
5. **Add `project_id` to task creation** — ensure every `POST /v2/tasks` call includes a valid `project_id`.
6. **Update list response handling** — parse the paginated envelope (`items`, `total`, `next_cursor`) instead of treating the response as a bare array.
7. **Implement cursor pagination** — if you fetch all tasks, loop through `next_cursor` pages instead of assuming a single response.
8. **Test against v2** — remove any v1 endpoint references and verify all calls succeed against the v2 API.

---

Upgrade now:

```
npm install @zrb/task-sdk@2
```