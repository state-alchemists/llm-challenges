# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2 and shows you exactly what to update in your code. If you are currently running v1, follow the checklist at the end to upgrade safely.

---

## Breaking Changes

### 1. API Version Prefix Required

All endpoints are now prefixed with `/v2/`. Requests to the old un-versioned paths will return `404`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.dev/tasks \
  -H "X-Auth-Token: <token>"
```

**After (v2):**
```bash
curl -X GET https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer <token>"
```

---

### 2. Authentication Header Changed

The custom `X-Auth-Token` header is removed. v2 requires a standard Bearer token in the `Authorization` header. Sending `X-Auth-Token` now returns `401 Unauthorized`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.dev/tasks/42 \
  -H "X-Auth-Token: my_api_key"
```

**After (v2):**
```bash
curl -X GET https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer my_api_token"
```

---

### 3. Task ID Changed from Integer to UUID

Task `id` fields are now UUID strings instead of integers. Update any code that assumes numeric IDs, performs arithmetic on IDs, or stores them as integer columns.

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

### 4. Field Rename: `done` → `completed`

The boolean flag on tasks is now called `completed`. Using `done` in request bodies or reading it from responses will fail or return `undefined`.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.dev/tasks/42 \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

### 5. `project_id` Is Now Required on Create

Creating a task without a `project_id` returns `422 Unprocessable Entity`. You must supply a valid project identifier in the request body.

**Before (v1):**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List Endpoints Return a Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`. You must update parsing logic that expects an array at the root of the response.

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

Pass the `next_cursor` value as the `?cursor=` query parameter to fetch the next page:

```bash
curl -X GET "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer <token>"
```

---

## Migration Checklist

Use this checklist to verify that your integration is fully migrated before switching traffic to v2.

- [ ] Update every endpoint URL to include the `/v2/` prefix.
- [ ] Replace the `X-Auth-Token` header with `Authorization: Bearer <token>` on all requests.
- [ ] Change any client-side storage or database schemas that store task `id` as an integer to use strings (UUIDs).
- [ ] Rename all references to the `done` field to `completed` in request bodies and response parsing.
- [ ] Add a `project_id` field to every task creation request.
- [ ] Update list-response parsing to read `response.items` instead of treating the response body as a bare array.
- [ ] Implement cursor-based pagination if your workflow iterates through all tasks.
- [ ] Run your test suite against the v2 endpoints in a staging environment.
- [ ] Rotate and update API tokens if your old tokens were scoped only to v1 endpoints.

---

## Upgrade Command

Install the latest v2 release:

```bash
pip install --upgrade zrb
```
