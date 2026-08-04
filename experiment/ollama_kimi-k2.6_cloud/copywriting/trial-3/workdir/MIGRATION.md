# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2. If you are already running v1, follow the sections below to update your code, then work through the checklist at the end before deploying.

---

## Breaking Changes

### 1. Endpoint URL Prefix

All API endpoints are now prefixed with `/v2/`.

**Before (v1):**
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The header `X-Auth-Token` has been replaced with a Bearer token in the `Authorization` header. Requests that still send `X-Auth-Token` will receive `HTTP 401 Unauthorized`.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers. This affects every endpoint that references a task by ID, as well as the shape of task objects in responses.

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

The boolean field indicating whether a task is finished has been renamed from `done` to `completed`. Update any request bodies, response parsing, and filter logic that references this field.

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

---

### 5. Task Creation Now Requires `project_id`

Creating a task now requires a `project_id` in the request body. Omitting it returns `HTTP 422 Unprocessable Entity`.

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

---

### 6. List Endpoints Return a Paginated Envelope

The `GET /v2/tasks` endpoint no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. Pass `?cursor=<next_cursor>` to fetch the next page.

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
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

Follow these steps in order before switching traffic to v2:

1. **Upgrade the CLI** — install the latest v2 binary (see command below).
2. **Rotate credentials** — generate a new API token and update the `Authorization: Bearer <token>` header in every client.
3. **Update base URLs** — prepend `/v2/` to all endpoint paths.
4. **Migrate ID handling** — replace any integer-based task IDs with UUID strings across databases, caches, and UI state.
5. **Rename `done` to `completed`** — update request bodies, response parsers, serializers, and any query filters that reference the old field name.
6. **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
7. **Adapt list consumers** — update any code that reads `GET /v2/tasks` to unwrap `response.items` instead of using the raw array, and implement cursor-based pagination if you currently paginate client-side.
8. **Run integration tests** — verify all CRUD flows, auth rejection, and pagination against a v2 instance before production cutover.

---

## Upgrade Command

Install or upgrade to v2:

```bash
zrb upgrade
```

After upgrading, confirm the version:

```bash
zrb --version
```

You should see `2.x.x` before proceeding with the checklist above.
