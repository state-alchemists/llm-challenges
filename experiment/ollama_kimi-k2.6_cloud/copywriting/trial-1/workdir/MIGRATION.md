# Zrb CLI v1 → v2 Developer Migration Guide

Zrb CLI v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and shows you exactly what to update in your code.

---

## Breaking Change 1: Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1)**
```bash
curl https://api.zrb.io/tasks
curl https://api.zrb.io/tasks/42
curl -X POST https://api.zrb.io/tasks
curl -X PUT https://api.zrb.io/tasks/42
curl -X DELETE https://api.zrb.io/tasks/42
```

**After (v2)**
```bash
curl https://api.zrb.io/v2/tasks
curl https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.io/v2/tasks
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Breaking Change 2: Authentication Header

The `X-Auth-Token` header is removed. v2 requires a Bearer token in the `Authorization` header. Requests sent with `X-Auth-Token` will receive HTTP 401.

**Before (v1)**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.io/tasks
```

**After (v2)**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.io/v2/tasks
```

---

## Breaking Change 3: Task `id` Changed from Integer to UUID String

Task identifiers are no longer integers. Every `id` is now a UUID string. Update any client-side logic that assumes an integer ID (numeric comparisons, auto-increment assumptions, URL formatting without URL-encoding, etc.).

**Before (v1)**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**
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

## Breaking Change 4: Field `done` Renamed to `completed`

The task status field is renamed from `done` to `completed`. This affects task objects in all responses and the `PUT` request body.

**Before (v1)**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "Updated title", "done": true}'
```

**After (v2)**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "Updated title", "completed": true}'
```

---

## Breaking Change 5: Task Creation Now Requires `project_id`

Creating a task without a `project_id` now returns HTTP 422. You must associate every new task with a project.

**Before (v1)**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2)**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

## Breaking Change 6: List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. Use `?cursor=<next_cursor>` to fetch subsequent pages.

**Before (v1)**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page:
```bash
curl "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer <your_api_token>"
```

---

## Step-by-Step Migration Checklist

- [ ] **Update your base URL or path prefix** to include `/v2/` on every endpoint.
- [ ] **Replace `X-Auth-Token`** with `Authorization: Bearer <token>` in all request headers.
- [ ] **Audit ID handling** in your codebase: remove any logic that assumes task IDs are integers (numeric sorts, arithmetic, etc.). Treat IDs as opaque UUID strings.
- [ ] **Rename every occurrence of `done`** to `completed` in request bodies and response parsing logic.
- [ ] **Add `project_id`** to all task creation calls; ensure the value is valid or obtain it from the new Projects API if needed.
- [ ] **Rewrite list-consumption logic** to unwrap tasks from the `items` array inside the paginated envelope and handle `next_cursor` pagination.
- [ ] **Run integration tests** against the v2 endpoints and verify every call returns the expected HTTP status and shape.

---

## Upgrade Command

```bash
zrb upgrade --to v2
```

After upgrading, run your test suite and walk through the checklist above to confirm a clean migration.
