# Migrating from Zrb CLI v1 to v2

This guide covers every breaking change in Zrb CLI v2 and how to update your code. If you are already running v1 in production, follow the sections below in order.

---

## Breaking Changes

### 1. API Version Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths will return `404`.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <token>" \
  https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <token>" \
  https://api.zrb.example/v2/tasks
```

---

### 2. Authentication Header

The custom `X-Auth-Token` header has been replaced with a standard Bearer token. Sending `X-Auth-Token` will now result in `401 Unauthorized`.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example/tasks/42
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 3. Task ID Format

Task IDs have changed from auto-incrementing integers to UUID strings. Update any client-side types, validation, or URL construction that assumes an integer `id`.

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

### 4. `done` Renamed to `completed`

The boolean field `done` is now called `completed`. Using the old key in request bodies or when reading responses will fail or silently ignore the field.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.example/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <token>" \
  -d '{"title": "Updated title", "done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "Updated title", "completed": true}'
```

---

### 5. Required `project_id` on Create

Creating a task now requires a `project_id`. Requests without it will return `422 Unprocessable Entity`.

**Before (v1):**
```bash
curl -X POST https://api.zrb.example/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <token>" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

### 6. Paginated List Responses

The `GET /tasks` endpoint no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. Pass `?cursor=<next_cursor>` to fetch the next page.

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

**Fetching the next page (v2):**
```bash
curl -H "Authorization: Bearer <token>" \
  "https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to roll out the v2 upgrade safely.

1. **Upgrade the CLI** to v2 locally and in CI.
2. **Update environment variables / secrets**: replace `X-Auth-Token` values with Bearer tokens if your token format changed.
3. **Update base URLs**: add `/v2` to all endpoint constants.
4. **Migrate ID types**: change task `id` fields from `int` / `number` to `string` (UUID) in your models, databases, and serialization logic.
5. **Rename `done` to `completed`** everywhere: request builders, response parsers, UI components, and test fixtures.
6. **Inject `project_id`** into all task creation flows. If your app does not yet have projects, create a default project and pass its ID.
7. **Rewrite list consumers**: unwrap `response.items` instead of using the raw array; implement cursor pagination if you iterate over large lists.
8. **Run integration tests** against the v2 endpoints and fix any `401` or `422` errors.
9. **Deploy** to staging, verify pagination and auth, then promote to production.

---

## Upgrade

Install v2 with pip:

```bash
pip install --upgrade zrb==2.0.0
```
