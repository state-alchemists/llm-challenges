# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change from v1 to v2 and how to update your integration.

## Breaking Changes

### 1. URL Prefix: `/tasks` → `/v2/tasks`

All endpoints now live under the `/v2/` prefix.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header: `X-Auth-Token` → `Bearer Token`

The `X-Auth-Token` header is no longer accepted. Switch to the `Authorization` header with a Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests with `X-Auth-Token` will receive **HTTP 401**.

---

### 3. Task ID: Integer → UUID String

Task IDs are now UUIDs instead of integers. Update any code that parses or stores task IDs.

**Before (v1):**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update type annotations, database columns, and serialization logic accordingly.

---

### 4. Field Rename: `done` → `completed`

The `done` boolean is renamed to `completed`.

**Before (v1):**
```json
{ "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "title": "Ship v2", "completed": true }
```

Update all field references in your code, templates, and storage.

---

### 5. New Required Field: `project_id` on Task Creation

Creating a task now requires a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1):**
```http
POST /v2/tasks
{
  "title": "New task title"
}
```

**After (v2):**
```http
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

If you don't have projects yet, create one via `POST /v2/projects` first.

---

### 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To paginate, pass `?cursor=<next_cursor>` on the next request.

---

## Migration Checklist

- [ ] Update all endpoint URLs to include `/v2/` prefix
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task ID type from `int` to `str` (UUID) in code and storage
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to task creation payloads
- [ ] Update list response handling to extract `items` from the envelope
- [ ] Implement cursor-based pagination for list endpoints
- [ ] Update any type annotations or serialization logic

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```

Or, if using the Go CLI:

```bash
go install github.com/zrb/cli/cmd@latest
```
