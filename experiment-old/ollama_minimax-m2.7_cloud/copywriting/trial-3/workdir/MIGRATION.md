# Zrb CLI Migration Guide: v1 → v2

v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and how to update your integration.

---

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header Changed

The auth header changed from `X-Auth-Token` to a Bearer token. Requests with the v1 header will receive `401 Unauthorized`.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

---

### 3. Task `id` Type Changed

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

### 4. Task Field Renamed

The `done` boolean is renamed to `completed`. Update all references in your code.

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

Creating a task now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**
```json
POST /v2/tasks
{
  "title": "New task"
}
```

**After (v2):**
```json
POST /v2/tasks
{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Format Changed

List endpoints return a paginated envelope instead of a bare array. Access items via `response.items`. Use `response.next_cursor` for subsequent pages.

**Before (v1):**
```json
[
  { "id": 1, "title": "Task one" },
  { "id": 2, "title": "Task two" }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "...", "title": "Task one", "completed": false, "project_id": "proj_abc123" },
    { "id": "...", "title": "Task two", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer`
- [ ] Update task ID parsing — expect UUID strings, not integers
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to every task creation request
- [ ] Update list response handling to extract `items` from envelope
- [ ] Implement cursor-based pagination using `next_cursor` for large lists
- [ ] Add a `project_id` field to task objects in your data model
- [ ] Update any tests or mocks to use v2 response shapes

---

## Upgrade Command

```bash
npm install zrb@latest
# or
pip install --upgrade zrb
```
