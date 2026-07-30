# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. If your integration is currently on v1, follow the sections below to update your code.

---

## Breaking Changes

### 1. API endpoints are now prefixed with `/v2/`

All endpoints have moved under the `/v2/` path namespace. Requests to the old v1 paths will return HTTP 404.

**Before (v1):**
```bash
# List tasks
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: $API_KEY"

# Create a task
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2):**
```bash
# List tasks
curl https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $API_TOKEN"

# Create a task
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

---

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

v2 uses standard Bearer token authentication. The legacy `X-Auth-Token` header is no longer accepted and will result in HTTP 401.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any client-side code that assumes numeric IDs.

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

---

### 4. Task field `done` renamed to `completed`

The boolean status field on tasks has been renamed from `done` to `completed`. Using `done` in write payloads will be ignored or rejected.

**Before (v1):**
```json
// Response body
{
  "id": 1,
  "title": "Ship v1",
  "done": true,
  "created_at": "..."
}

// Update payload
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```json
// Response body
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "..."
}

// Update payload
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` will return HTTP 422. You must associate every new task with a project.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update any code that iterates over the response directly.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: $API_KEY"
```

Response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
// Client code example
const tasks = await response.json();
tasks.forEach(task => console.log(task.title));
```

**After (v2):**
```bash
curl "https://api.zrb.io/v2/tasks?limit=20" \
  -H "Authorization: Bearer $API_TOKEN"
```

Response:
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```javascript
// Client code example
const data = await response.json();
const tasks = data.items;
tasks.forEach(task => console.log(task.title));

// Fetch next page
const nextCursor = data.next_cursor;
if (nextCursor) {
  const nextPage = await fetch(`https://api.zrb.io/v2/tasks?cursor=${nextCursor}`);
}
```

---

## Migration Checklist

Use this checklist to ensure your integration is fully updated before deploying to production.

- [ ] **Update endpoint URLs** — prefix all paths with `/v2/`.
- [ ] **Replace auth header** — switch from `X-Auth-Token` to `Authorization: Bearer <token>`.
- [ ] **Update `id` handling** — treat task IDs as UUID strings, not integers.
- [ ] **Rename `done` to `completed`** — update all reads and writes of the task status field.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` payload includes a valid `project_id`.
- [ ] **Handle paginated list responses** — extract tasks from the `items` key and implement cursor pagination using `next_cursor`.
- [ ] **Smoke-test all endpoints** — verify list, get, create, update, and delete operations in a staging environment.
- [ ] **Rotate or regenerate API tokens** — if your v1 keys are incompatible with Bearer format, generate fresh tokens in the v2 dashboard.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g @zrb/cli@latest
```

Verify the installation:

```bash
zrb --version
# Expected output: 2.x.x
```
