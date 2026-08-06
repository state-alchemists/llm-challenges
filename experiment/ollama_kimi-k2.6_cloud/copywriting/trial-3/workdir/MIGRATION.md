# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change in Zrb CLI v2 and how to update your code.

---

## 1. Base URL Prefix Changed

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks
```

---

## 2. Authentication Header Changed

The `X-Auth-Token` header is removed. v2 uses a Bearer token in the `Authorization` header. Requests with the old header will receive HTTP 401.

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

## 3. Task `id` Changed from Integer to UUID String

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any code that treats `id` as an integer or assumes numeric ordering.

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

## 4. Field `done` Renamed to `completed`

The boolean field indicating task completion is now named `completed`. The old name `done` is no longer accepted in request bodies and will not appear in responses.

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

## 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` now returns HTTP 422. You must include a valid project identifier in the request body.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## 6. List Endpoints Return a Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. Use the `cursor` query parameter to paginate through results.

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

**Pagination request:**
```bash
curl "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer <token>"
```

---

## Migration Checklist

Use this checklist to ensure your codebase is fully migrated.

- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>` headers.
- [ ] Update task `id` handling: store and parse IDs as UUID strings, not integers.
- [ ] Rename all references to the `done` field to `completed` in request bodies and response parsing.
- [ ] Add `project_id` to every task creation request and validate it server-side.
- [ ] Update list-task response parsing: read tasks from `items`, not the top-level array.
- [ ] Implement pagination logic using `cursor` and `next_cursor` for list endpoints.
- [ ] Run integration tests against the v2 API to verify all flows.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g zrb-cli@latest
```

Or with your package manager of choice:

```bash
# Yarn
yarn global add zrb-cli@latest

# pnpm
pnpm add -g zrb-cli@latest
```
