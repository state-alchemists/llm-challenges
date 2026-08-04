# Zrb CLI v1 to v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2 and provides concrete before/after examples to get your code running again.

---

## Overview

Zrb v2 introduces projects, pagination, and stricter authentication. Several fields, headers, and response shapes have changed. This guide walks through each breaking change and shows exactly what to update in your code.

---

## Breaking Changes

### 1. API endpoints are now version-prefixed

All endpoints now live under `/v2/`. Requests to the old unprefixed paths will return `404`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.dev/tasks
curl -X POST https://api.zrb.dev/tasks
curl -X PUT https://api.zrb.dev/tasks/42
curl -X DELETE https://api.zrb.dev/tasks/42
```

**After (v2):**
```bash
curl -X GET https://api.zrb.dev/v2/tasks
curl -X POST https://api.zrb.dev/v2/tasks
curl -X PUT https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication header changed to Bearer token

The custom `X-Auth-Token` header is removed. v2 uses a standard `Authorization: Bearer` header. Requests sent with `X-Auth-Token` will receive `401 Unauthorized`.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.dev/v2/tasks
```

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any code that assumes numeric IDs or performs integer arithmetic on IDs.

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

The boolean field indicating task status is now named `completed`. Update all reads, writes, and serializations.

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

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` will return `422 Unprocessable Entity`. Every task must belong to a project.

**Before (v1):**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a plain JSON array. It now returns an envelope object containing `items`, `total`, and `next_cursor`. If you were iterating directly over the response body, you must now iterate over `response.items`.

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
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, pass the cursor as a query parameter:

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to upgrade your codebase systematically.

- [ ] **Update base URLs**: Add `/v2/` prefix to all API endpoints.
- [ ] **Swap auth header**: Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate IDs to UUIDs**: Treat task IDs as strings, not integers. Update storage, URL construction, and comparison logic.
- [ ] **Rename `done` to `completed`**: Update request bodies, response parsing, and any UI bindings.
- [ ] **Add `project_id` to task creation**: Ensure every `POST /v2/tasks` payload includes a valid `project_id`.
- [ ] **Adapt list parsing**: Expect a paginated envelope from `GET /v2/tasks`. Read tasks from `.items`, check `.next_cursor` for pagination, and handle `.total` if needed.
- [ ] **Run integration tests**: Verify all task lifecycle operations (create, read, update, delete, list) against the v2 API.
- [ ] **Update documentation**: Reflect v2 conventions in any internal API docs or client SDKs.

---

## Upgrade Command

Install the latest v2 CLI globally:

```bash
npm install -g zrb-cli@latest
```

Verify the installed version:

```bash
zrb --version
```

You are now ready to migrate. If you run into undocumented edge cases, open an issue on the [Zrb CLI repository](https://github.com/zrbdev/zrb-cli).
