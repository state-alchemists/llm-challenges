# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, paginated list responses, and stricter authentication. This guide covers every breaking change you need to address before the v1 endpoints are fully deprecated.

---

## 1. Endpoint Base Path

All endpoints are now prefixed with `/v2/`.

### Before (v1)
```bash
curl -X GET https://api.zrb.io/tasks
curl -X POST https://api.zrb.io/tasks
```

### After (v2)
```bash
curl -X GET https://api.zrb.io/v2/tasks
curl -X POST https://api.zrb.io/v2/tasks
```

---

## 2. Authentication Header

The `X-Auth-Token` header is removed. v2 requires a Bearer token in the `Authorization` header. Requests using the old header will receive HTTP 401.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.io/tasks
```

### After (v2)
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.io/v2/tasks
```

---

## 3. Task ID Type Changed

`id` is no longer an integer. All task IDs are now UUID strings.

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

**Action required:** Update any code that treats `id` as an integer, generates IDs client-side, or uses integer comparison logic.

---

## 4. `done` Renamed to `completed`

The task status field is renamed from `done` to `completed`. Using the old field name in request bodies will be ignored (or fail validation on create/update).

### Before (v1)
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

### After (v2)
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

**Action required:** Rename `done` to `completed` in request payloads and response parsing across your codebase.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

### Before (v1)
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

### After (v2)
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

**Action required:** Ensure your task-creation flows now collect or derive a `project_id` before calling the API.

---

## 6. List Endpoints Return Paginated Envelopes

List endpoints no longer return a bare array. They now return a paginated envelope containing `items`, `total`, and `next_cursor`.

### Before (v1)
**Request:**
```bash
curl https://api.zrb.io/tasks
```

**Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
**Request:**
```bash
curl "https://api.zrb.io/v2/tasks?limit=20"
```

**Response:**
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

**Action required:**
- Update list-parsing logic to read from the `items` key.
- Implement pagination using the `next_cursor` value passed as the `cursor` query parameter.

---

## Migration Checklist

Use this checklist to ensure your upgrade is complete:

- [ ] **Update base URLs** to `/v2/` across all API calls.
- [ ] **Replace auth header** `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Audit ID handling** — replace integer IDs with UUID strings everywhere (requests, responses, storage, comparisons).
- [ ] **Rename field** `done` → `completed` in all request payloads and response parsing.
- [ ] **Add `project_id`** to every task creation payload.
- [ ] **Refactor list endpoints** to parse the paginated envelope (`items`, `total`, `next_cursor`) and implement cursor-based pagination.
- [ ] **Run integration tests** against the v2 endpoints in a staging environment.
- [ ] **Update internal documentation** and SDK wrappers for your team.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g @zrb/cli@latest
```

Or upgrade your local project dependency:

```bash
npm install @zrb/cli@^2.0.0
```

After upgrading, verify the version:

```bash
zrb --version
```
