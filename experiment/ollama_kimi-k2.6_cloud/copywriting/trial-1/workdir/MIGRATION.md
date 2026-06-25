# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change in Zrb CLI v2 and how to update your integration.

## Overview

v2 introduces projects, pagination, and stricter authentication. If you are already integrating with v1, you must update request URLs, headers, payload shapes, and response handling.

## Breaking Changes

### 1. Base URL Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.example/tasks
curl -X POST https://api.zrb.example/tasks
curl -X PUT https://api.zrb.example/tasks/42
curl -X DELETE https://api.zrb.example/tasks/42
```

**After (v2):**
```bash
curl -X GET https://api.zrb.example/v2/tasks
curl -X POST https://api.zrb.example/v2/tasks
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The `X-Auth-Token` header is removed. Use an `Authorization: Bearer` token instead. Requests sent with the old header will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.example/v2/tasks
```

---

### 3. Task `id` Type Changed from Integer to UUID

Task identifiers are no longer integers. They are now UUID strings. Update any client-side types, validation, or URL construction that assumes an integer `id`.

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

### 4. Field `done` Renamed to `completed`

The boolean flag indicating whether a task is finished has been renamed from `done` to `completed`. This affects payloads in responses and updates.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.example/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "Updated title", "done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "Updated title", "completed": true}'
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it will return HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.example/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List Endpoints Return a Paginated Envelope

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
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetch the next page by passing the cursor as a query parameter:

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Step-by-Step Migration Checklist

Use this checklist to ensure your integration is fully migrated.

- [ ] **Update base URLs** — prepend `/v2/` to all endpoint paths.
- [ ] **Replace auth header** — swap `X-Auth-Token` for `Authorization: Bearer <token>`.
- [ ] **Update ID handling** — change task `id` fields from integers to UUID strings in types, validation, and URL building.
- [ ] **Rename `done` to `completed`** — update all request bodies and response parsers that reference the old field name.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
- [ ] **Handle paginated list responses** — update `GET /v2/tasks` consumers to read `response.items` instead of the top-level array, and implement cursor-based pagination if needed.
- [ ] **Verify error handling** — confirm your client correctly handles HTTP 401 for invalid auth and HTTP 422 for missing `project_id`.

## Upgrade Command

Install the latest v2 CLI globally:

```bash
npm install -g @zrb/cli@latest
```
