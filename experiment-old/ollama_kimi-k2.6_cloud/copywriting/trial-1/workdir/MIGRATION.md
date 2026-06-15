# Zrb Task API — v1 to v2 Migration Guide

Zrb CLI v2 is now available. This guide covers every breaking change you need to address before the v1 API is retired.

## Breaking Changes

### 1. Endpoint prefix changed

All task endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN"
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Authentication header changed

The `X-Auth-Token` header is removed. Use a Bearer token instead. Requests sent with the old header will receive HTTP 401.

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

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings. Update any client-side types, parsing, or database columns that assumed an integer.

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

### 4. Task field `done` renamed to `completed`

Update all read and write references from `done` to `completed`.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` will return HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6g7-8901-bcde-fg2345678901", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Use `?cursor=<next_cursor>` to fetch subsequent pages, and `?limit=<n>` to control page size (default is 20).

## Migration Checklist

- [ ] Replace every `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Add `/v2` prefix to all task endpoint URLs
- [ ] Update task `id` types from `int` to `string` (UUID) in your models and databases
- [ ] Rename every read/write of the `done` field to `completed`
- [ ] Ensure every task creation payload includes a `project_id`
- [ ] Update list-task consumers to unwrap `response.items` instead of the top-level array
- [ ] Add pagination logic using `next_cursor` and `limit` for list endpoints
- [ ] Run your integration test suite against the v2 endpoints

## Upgrade Command

```bash
zrb update --to v2
```
