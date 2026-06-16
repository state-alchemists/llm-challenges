# Zrb Task API v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from the Zrb Task API v1 to v2. If you are already integrating with v1, follow the sections below and the checklist at the end.

## Breaking Changes

### 1. Endpoint prefix changed to `/v2/`

All endpoints now live under the `/v2/` path prefix.

**Before (v1):**
```bash
curl https://api.zrb.example/tasks
curl https://api.zrb.example/tasks/42
```

**After (v2):**
```bash
curl https://api.zrb.example/v2/tasks
curl https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication header changed

The custom `X-Auth-Token` header is replaced by a standard Bearer token.

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

Requests sent with the old `X-Auth-Token` header will receive `HTTP 401 Unauthorized`.

### 3. Task `id` changed from integer to UUID

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

Update any client-side types, database columns, or URL routing that assumes integer IDs.

### 4. Field `done` renamed to `completed`

The boolean field indicating task status is now called `completed`.

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

This affects both the response body and the request body for create and update operations.

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` now returns `HTTP 422 Unprocessable Entity`.

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
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope.

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
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_def456", "created_at": "..."}
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

## Migration Checklist

Use this checklist to upgrade your integration:

- [ ] **Update base URL** — prepend `/v2/` to all endpoint paths.
- [ ] **Rotate authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate IDs to UUID** — change task `id` fields from integer to string/UUID in your types, models, and routes.
- [ ] **Rename `done` to `completed`** — update request bodies, response parsing, and any conditional logic.
- [ ] **Supply `project_id` on creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
- [ ] **Handle paginated lists** — update list consumers to read from the `items` array and support cursor-based pagination.
- [ ] **Test end-to-end** — run your full suite against the v2 endpoints before switching production traffic.

## Upgrade Command

Install or upgrade the Zrb CLI to v2:

```bash
pip install --upgrade zrb-cli>=2.0.0
```
