# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2 and shows you exactly what to update in your code.

---

## Breaking Changes

### 1. Base URL Version Prefix

All endpoints now require the `/v2/` prefix. Requests to the legacy unversioned paths will fail.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The custom `X-Auth-Token` header has been replaced by a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

> **Impact:** Requests sent with `X-Auth-Token` will receive HTTP `401 Unauthorized`.

---

### 3. Task `id` Changed from Integer to UUID String

Task identifiers are now UUID strings instead of auto-incrementing integers.

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

> **Impact:** Update any client-side storage, caching, or parsing logic that assumes `id` is a number.

---

### 4. Task Field `done` Renamed to `completed`

The boolean flag indicating whether a task is finished has been renamed.

**Before (v1):**
```json
{
  "done": false
}
```

**After (v2):**
```json
{
  "completed": false
}
```

> **Impact:** Update payloads when creating or updating tasks, and adjust any UI bindings that reference `done`.

---

### 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` is no longer allowed and will return HTTP `422 Unprocessable Entity`.

**Before (v1):**
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
```http
POST /v2/tasks
Content-Type: application/json
Authorization: Bearer <your_api_token>

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

> **Impact:** Ensure you have a valid `project_id` before issuing create requests.

---

### 6. List Endpoints Return a Paginated Envelope

The list endpoint no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

> **Impact:** Access the task list through `response.items` instead of using the response directly. Use `?cursor=<next_cursor>` to paginate.

---

## Step-by-Step Migration Checklist

- [ ] Update the base URL in all HTTP clients to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Migrate any stored task IDs from integers to UUID strings (or treat them as strings going forward).
- [ ] Rename all references to the `done` field to `completed` in request bodies and UI state.
- [ ] Add a `project_id` field to every task creation request.
- [ ] Wrap task-list consumers to read from the `items` key in the paginated envelope.
- [ ] Implement pagination support using the `cursor` and `limit` query parameters.
- [ ] Run integration tests against a v2 sandbox before deploying to production.

---

## Upgrade Command

Install the latest CLI globally:

```bash
npm install -g @zrb/cli@latest
```

Or upgrade your local project dependency:

```bash
npm install @zrb/cli@^2.0.0
```
