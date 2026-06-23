# Zrb Task API v1 → v2 Migration Guide

This guide covers every breaking change between the Zrb Task API v1 and v2. If you are already running a v1 integration, follow the sections below in order and use the checklist at the end to verify your migration.

---

## Overview of Breaking Changes

| # | Change | Impact |
|---|--------|--------|
| 1 | API version prefix | All endpoint paths now require `/v2/` |
| 2 | Authentication header | `X-Auth-Token` replaced by `Authorization: Bearer` |
| 3 | Task `id` type | Integer IDs are now UUID strings |
| 4 | Task field rename | `done` renamed to `completed` |
| 5 | Required `project_id` | Task creation now requires a `project_id` |
| 6 | Paginated list response | List endpoints return an envelope object instead of a bare array |

---

## 1. API Version Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old unprefixed paths will return HTTP 404.

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

## 2. Authentication Header

The `X-Auth-Token` header is removed. Send a Bearer token via the `Authorization` header instead. Requests using the old header will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     https://api.zrb.example/v2/tasks
```

---

## 3. Task `id` Type Changed to UUID

Task identifiers are now UUID strings. If your code casts or stores `id` as an integer, update your types and serialization logic.

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

## 4. Task Field `done` Renamed to `completed`

The boolean flag indicating task completion has been renamed from `done` to `completed`. Update all request bodies and response parsing accordingly.

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

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` in the request body. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.example/tasks \
     -H "Content-Type: application/json" \
     -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.example/v2/tasks \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <your_api_token>" \
     -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## 6. Paginated List Response

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`.

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
curl "https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20" \
     -H "Authorization: Bearer <your_api_token>"
```

---

## Migration Checklist

Use this checklist to verify your codebase is fully migrated before pointing traffic at v2.

- [ ] **Prefix all endpoint URLs** with `/v2/`
- [ ] **Replace authentication header** — remove `X-Auth-Token`, add `Authorization: Bearer <token>`
- [ ] **Update Task `id` type** from `int` / `number` to `string` (UUID)
- [ ] **Rename `done` to `completed`** in all request bodies, response parsing, and database schemas
- [ ] **Add `project_id` to task creation** payloads; ensure a valid project exists before creating tasks
- [ ] **Update list-task consumers** to read from `response.items` instead of the top-level array
- [ ] **Add pagination handling** for list endpoints (use `next_cursor` and `limit` query params)
- [ ] **Run integration tests** against the v2 environment and confirm all task CRUD operations pass

---

## Upgrade Command

Install the v2 CLI to gain access to the updated commands and helpers:

```bash
zrb update --version 2
```
