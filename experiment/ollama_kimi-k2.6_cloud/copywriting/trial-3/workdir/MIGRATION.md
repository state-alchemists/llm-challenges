# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. **This guide covers every breaking change** you need to address when upgrading from v1.

---

## 1. Base URL Prefix

**Breaking change:** All endpoints are now prefixed with `/v2/`.

Requests to the old v1 paths will return `404`.

### Before (v1)
```bash
curl https://api.zrb.example/tasks
curl https://api.zrb.example/tasks/42
```

### After (v2)
```bash
curl https://api.zrb.example/v2/tasks
curl https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

**Breaking change:** The `X-Auth-Token` header is removed. v2 requires a Bearer token in the `Authorization` header.

Requests using `X-Auth-Token` will receive `401 Unauthorized`.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example/tasks
```

### After (v2)
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.example/v2/tasks
```

---

## 3. Task `id` Type Changed from Integer to UUID

**Breaking change:** Task identifiers are now UUID strings instead of auto-incrementing integers.

Update any client-side code that assumes `id` is an integer (e.g., numeric comparisons, database schemas with `INTEGER` columns, or URL routing patterns constrained to digits).

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
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

**Breaking change:** The boolean field indicating task completion is now named `completed`.

Update serialization, deserialization, and any query or filter logic referencing `done`.

### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

## 5. Task Creation Requires `project_id`

**Breaking change:** `POST /v2/tasks` now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

### Before (v1)
```bash
curl -X POST https://api.zrb.example/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

### After (v2)
```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## 6. List Endpoints Return a Paginated Envelope

**Breaking change:** `GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`.

Update any code that directly iterates over the response body as an array.

### Before (v1)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
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

Use this checklist to ensure a complete upgrade:

- [ ] Update all API client base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Change Task `id` handling from integer to UUID string.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Add `project_id` to every Task creation request.
- [ ] Update List Tasks response parsing to expect a paginated envelope (`items`, `total`, `next_cursor`).
- [ ] Implement cursor-based pagination if your workflow fetches multiple pages.
- [ ] Run integration tests against the v2 sandbox before deploying to production.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g zrb@latest
```

Verify the installation:

```bash
zrb --version
```
