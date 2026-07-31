# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading from v1.

---

## Breaking Changes

### 1. API Base URL Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.io/tasks
curl -X POST https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -X GET https://api.zrb.io/v2/tasks
curl -X POST https://api.zrb.io/v2/tasks
```

---

### 2. Authentication Header

The `X-Auth-Token` header is removed. v2 uses a standard Bearer token via the `Authorization` header. Requests with the old header will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.io/v2/tasks
```

---

### 3. Task ID Type Changed from Integer to UUID

Task `id` fields are now UUID strings instead of integers. This affects deserialization, type annotations, and any logic that assumes integer IDs.

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

The boolean field indicating task status has been renamed from `done` to `completed`. Update your request bodies and response parsing.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List Endpoints Return Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`.

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

To fetch the next page, pass the cursor as a query parameter:

```bash
curl "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to ensure your codebase is fully migrated:

- [ ] Update all API client base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update Task model / struct / type definitions so `id` is a UUID string, not an integer.
- [ ] Rename all references to the `done` field to `completed` in request bodies and response parsing.
- [ ] Ensure all task creation calls include a valid `project_id`.
- [ ] Update list-task consumers to read tasks from the `items` key inside the paginated envelope.
- [ ] Add pagination handling (cursor + limit) if your application needs to iterate through all tasks.
- [ ] Run integration tests against the v2 endpoints and verify HTTP status codes.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
zrb self-update --version 2
```
