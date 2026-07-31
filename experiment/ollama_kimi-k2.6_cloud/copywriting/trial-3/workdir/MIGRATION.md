# Zrb CLI v1 → v2 Migration Guide

This guide helps you migrate your existing v1 integrations to Zrb CLI v2. v2 introduces projects, cursor-based pagination, and stricter authentication. **v1 is deprecated and will be removed in a future release.**

---

## Breaking Changes

### 1. Base URL Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.io/tasks
curl -X POST https://api.zrb.io/tasks
curl -X PUT https://api.zrb.io/tasks/42
curl -X DELETE https://api.zrb.io/tasks/42
```

**After (v2):**
```bash
curl -X GET https://api.zrb.io/v2/tasks
curl -X POST https://api.zrb.io/v2/tasks
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The `X-Auth-Token` header is removed. v2 requires a Bearer token in the `Authorization` header.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.io/v2/tasks
```

> **Note:** Requests sent with the old `X-Auth-Token` header will receive HTTP 401.

---

### 3. Task `id` Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any code that assumes `id` is an integer (e.g., numeric comparisons, integer parsing, or URL construction).

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

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task status is now named `completed`. Using `done` in request bodies or expecting it in responses will fail or silently omit the field.

**Before (v1):**
```json
// Request body
{
  "title": "Updated title",
  "done": true
}

// Reading response
const isDone = task.done;
```

**After (v2):**
```json
// Request body
{
  "title": "Updated title",
  "completed": true
}

// Reading response
const isCompleted = task.completed;
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

### 6. List Endpoints Return a Paginated Envelope

`GET /tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update any code that iterates over the raw array.

**Before (v1):**
```json
// Response
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
// Client code
const tasks = await fetch('/tasks').then(r => r.json());
tasks.forEach(task => console.log(task.title));
```

**After (v2):**
```json
// Response
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```javascript
// Client code
const page = await fetch('/v2/tasks').then(r => r.json());
page.items.forEach(task => console.log(task.title));

// Fetch next page
const nextPage = await fetch(`/v2/tasks?cursor=${page.next_cursor}`).then(r => r.json());
```

> **Note:** v2 list endpoints also accept an optional `limit` query parameter (default 20).

---

## Migration Checklist

Use this checklist to ensure your codebase is fully migrated before deploying to production.

- [ ] **Update base URLs** — prepend `/v2/` to all endpoint paths (`/tasks` → `/v2/tasks`).
- [ ] **Rotate authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate `id` handling** — treat task IDs as strings (UUIDs), not integers. Update storage, URL building, and comparison logic.
- [ ] **Rename `done` to `completed`** — update request payloads and response parsing for create and update operations.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
- [ ] **Adapt list consumers** — unwrap tasks from the paginated envelope (`response.items`) and implement cursor-based pagination if you fetch more than one page.
- [ ] **Run integration tests** — verify all CRUD flows and edge cases (404s, 401s, 422s) against the v2 API.
- [ ] **Update documentation** — refresh internal docs, SDKs, and client examples to reflect v2 semantics.

---

## Upgrade Command

Install the latest v2 CLI globally:

```bash
npm install -g zrb-cli@latest
```

After installation, confirm the version:

```bash
zrb --version
```

For detailed v2 API reference, see [`v2_spec.md`](v2_spec.md).
