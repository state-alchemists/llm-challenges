# Zrb CLI v1 to v2 Migration Guide

This guide covers every breaking change from v1 to v2 and how to update your code.

## Breaking Changes

### 1. Endpoint Path Prefix

All endpoints are now versioned under `/v2/`. Requests to the old paths will return `404`.

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

### 2. Authentication Header

The auth header changed from `X-Auth-Token` to a Bearer token. Requests using the old header will receive `401 Unauthorized`.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

---

### 3. Task `id` Type: Integer to UUID

Task IDs are now UUID strings instead of integers. Update any code that parses or stores task IDs.

**Before (v1):**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

---

### 4. Task Field Renamed: `done` to `completed`

The `done` boolean is renamed to `completed`. Update all request bodies and response parsing.

**Before (v1):**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true }
```

For update requests:

**Before (v1):**
```json
{ "done": true }
```

**After (v2):**
```json
{ "completed": true }
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**
```json
{ "title": "New task title" }
```

**After (v2):**
```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

---

### 6. List Response: Paginated Envelope

List endpoints return a paginated envelope instead of a bare array. Access tasks via the `items` field. Use `next_cursor` for pagination.

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
    { "id": "...", "title": "Buy milk", "completed": false },
    { "id": "...", "title": "Ship v2", "completed": true }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`.

---

## Migration Checklist

- [ ] Update all endpoint paths to include `/v2/` prefix
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Update task ID handling: change integer fields/types to UUID strings
- [ ] Rename all `done` fields to `completed` in request bodies and response parsing
- [ ] Add `project_id` to every task creation request
- [ ] Update list response parsing to read from `items` array inside the envelope
- [ ] Implement cursor-based pagination for list endpoints if you fetch multiple pages
- [ ] Update any saved task IDs (database, cache, config) from integers to UUID strings
- [ ] Update API documentation references and internal tooling

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```
