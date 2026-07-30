# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and how to update your code.

---

## 1. Base URL Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```bash
curl -X GET https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -X GET https://api.zrb.io/v2/tasks
```

---

## 2. Authentication Header

The authentication header has changed from `X-Auth-Token` to a Bearer token. Requests using the old header will receive HTTP 401.

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

## 3. Task ID Type

Task IDs have changed from auto-incrementing integers to UUID strings. Update any code that assumes integer IDs.

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

## 4. Task Field Rename: `done` → `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.io/tasks/1 \
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

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it will return HTTP 422.

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

## 6. Paginated List Response

The list tasks endpoint no longer returns a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`.

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
curl -X GET "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to ensure your codebase is fully migrated:

- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update Task model / struct / type to use UUID strings for `id`.
- [ ] Rename the `done` field to `completed` in all requests and responses.
- [ ] Add `project_id` to all task creation payloads.
- [ ] Update list-tasks response handling to expect a paginated envelope (`items`, `total`, `next_cursor`).
- [ ] Implement pagination logic using `cursor` and `limit` query parameters if your UI requires it.
- [ ] Run your integration tests against the v2 endpoints.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g @zrb/cli@latest
```

Verify your version:

```bash
zrb --version
```

---

*If you encounter issues during migration, consult the full [v2 specification](v2_spec.md) or open a discussion in the developer community.*
