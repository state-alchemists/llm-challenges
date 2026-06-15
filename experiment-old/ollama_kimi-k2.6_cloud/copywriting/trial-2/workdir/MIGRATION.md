# Zrb CLI v1 → v2 Migration Guide

## Overview

Zrb CLI v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and provides before/after examples to help you migrate existing integrations.

---

## Breaking Changes

### 1. Endpoint Base Path Changed

All API endpoints are now prefixed with `/v2/`. Requests to the old paths will return HTTP 404.

**Before (v1):**
```bash
curl -H "X-Auth-Token: $TOKEN" \
  https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.zrb.io/v2/tasks
```

---

### 2. Authentication Header Changed

The `X-Auth-Token` header is removed. v2 uses a standard Bearer token in the `Authorization` header. Requests that still send `X-Auth-Token` will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.io/tasks/42
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 3. Task `id` Changed from Integer to UUID String

The `id` field on tasks is now a UUID string instead of an auto-assigned integer. Update any client-side models, URL construction logic, or database schemas that assume integer IDs.

**Before (v1) — Task object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — Task object:**
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

### 4. `done` Renamed to `completed`

The boolean field indicating task completion is now named `completed`. Using `done` in request payloads will be ignored or may cause validation errors.

**Before (v1) — Update task:**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2) — Update task:**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

### 5. Task Creation Now Requires `project_id`

Creating a task now requires a `project_id` field in the request body. Omitting it returns HTTP 422 Unprocessable Entity.

**Before (v1) — Create task:**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2) — Create task:**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List Endpoints Return Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`.

**Before (v1) — Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — Response:**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_1", "created_at": "..."},
    {"id": "d4e5f6a7-...", "title": "Ship v2", "completed": true, "project_id": "proj_1", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to migrate your codebase incrementally:

- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>` in all HTTP clients
- [ ] Prefix all endpoint URLs with `/v2/`
- [ ] Update client-side task models: change `id` from `int` to `string` (UUID)
- [ ] Rename the `done` field to `completed` in all serializers, models, and request/response payloads
- [ ] Add `project_id` to all task creation calls and ensure it is populated before sending
- [ ] Update list-task response parsing: expect a paginated envelope (`{ items, total, next_cursor }`) instead of a bare array
- [ ] Add pagination logic: check for `next_cursor` and loop until all pages are fetched
- [ ] Run integration tests against the v2 endpoints before deploying to production

---

## Upgrade Command

Install the v2 CLI to get the latest client and validation tools:

```bash
pip install --upgrade zrb==2.0.0
```

If you encounter issues during migration, open an issue at [github.com/state-alchemists/zrb](https://github.com/state-alchemists/zrb).
