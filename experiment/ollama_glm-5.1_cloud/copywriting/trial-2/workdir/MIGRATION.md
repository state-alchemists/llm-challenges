# Migrating from Zrb CLI v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change with before/after examples so you can update your integrations quickly.

---

## Breaking Changes

### 1. All endpoints are prefixed with `/v2/`

Every endpoint path now starts with `/v2/`. Requests to the old paths will return `404`.

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

If you set a base URL in your client, change it once:

```js
// Before
const baseURL = "https://api.zrb.dev";

// After
const baseURL = "https://api.zrb.dev/v2";
```

### 2. Authentication header changed

The `X-Auth-Token` header is no longer accepted. Requests using it receive `HTTP 401`. Use a standard `Authorization: Bearer` header instead.

**Before (v1):**

```sh
curl -H "X-Auth-Token: abc123" https://api.zrb.dev/tasks
```

**After (v2):**

```sh
curl -H "Authorization: Bearer abc123" https://api.zrb.dev/v2/tasks
```

In code:

```js
// Before
headers: { "X-Auth-Token": apiKey }

// After
headers: { "Authorization": `Bearer ${apiKey}` }
```

### 3. Task `id` changed from integer to UUID string

Task IDs are no longer auto-incrementing integers. They are now UUID strings.

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

**Impact:** Any code that stores, compares, or serializes task IDs as integers must be updated to handle strings. URL paths referencing tasks by ID also change:

```js
// Before
fetch(`/tasks/${taskId}`);

// After — taskId is now a UUID string
fetch(`/v2/tasks/${taskId}`);
```

If your database or models typed the ID column as an integer, migrate it to a string/UUID type before switching to v2.

### 4. Field `done` renamed to `completed`

The boolean field `done` on a task object is now called `completed`.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

This affects both **responses** and **request bodies** on update:

```js
// Before — marking a task complete
await fetch("/tasks/42", {
  method: "PUT",
  body: JSON.stringify({ done: true })
});

// After
await fetch(`/v2/tasks/${taskId}`, {
  method: "PUT",
  headers: { "Authorization": `Bearer ${apiKey}` },
  body: JSON.stringify({ completed: true })
});
```

Any code that reads `task.done` or sends `"done": ...` must be updated:

```js
// Before
if (task.done) { ... }

// After
if (task.completed) { ... }
```

### 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `HTTP 422`.

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

```js
// Before
await fetch("/tasks", {
  method: "POST",
  body: JSON.stringify({ title: "New task title" })
});

// After
await fetch("/v2/tasks", {
  method: "POST",
  headers: { "Authorization": `Bearer ${apiKey}` },
  body: JSON.stringify({
    title: "New task title",
    project_id: "proj_abc123"
  })
});
```

If you don't yet have a project concept, create a default project via the v2 projects API and use its ID for all existing task creation calls.

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages. The default page size is 20.

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
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Code that expected a top-level array must now read `response.items`:

```js
// Before
const tasks = await response.json();

// After
const { items, total, next_cursor } = await response.json();
const tasks = items;
```

To iterate all tasks across pages:

```js
let allTasks = [];
let cursor;

do {
  const url = cursor
    ? `/v2/tasks?cursor=${cursor}`
    : "/v2/tasks";
  const res = await fetch(url, { headers: { "Authorization": `Bearer ${apiKey}` } });
  const { items, total, next_cursor } = await res.json();
  allTasks.push(...items);
  cursor = next_cursor;
} while (cursor);
```

---

## Migration Checklist

- [ ] **Update base URL** — prepend `/v2` to all endpoint paths (or set a base URL with `/v2` included).
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Update ID handling** — change task ID storage, comparisons, and URL construction from integer to UUID string.
- [ ] **Rename `done` to `completed`** — in all response reads and request bodies.
- [ ] **Add `project_id` to task creation** — create a default project if needed, then include `project_id` in every `POST /v2/tasks` call.
- [ ] **Parse paginated envelope** — update list-endpoint consumers to read `.items` instead of treating the response as a bare array; implement cursor-based pagination where needed.

---

## Upgrade

```sh
npm install zrb-cli@2
```