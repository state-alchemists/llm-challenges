# Zrb CLI Migration Guide from v1 to v2

This guide outlines the breaking changes between version 1 and version 2 of the Zrb Task API. Developers using v1 should review the changes carefully and follow the migration checklist at the end of this document.

## Breaking Changes

### 1. API Endpoint Prefix
**Change:** All endpoints are now prefixed with `/v2/`.

**Before:**
```
GET /tasks
```

**After:**
```
GET /v2/tasks
```

---

### 2. Authentication Header Change
**Change:** The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.

**Before:**
```
X-Auth-Token: <your_api_key>
```

**After:**
```
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
**Change:** The type of `id` in the Task object has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After:**
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

### 4. Renaming of `done` to `completed`
**Change:** The field `done` has been renamed to `completed` in the Task object.

**Before:**
```json
{
  "done": false
}
```

**After:**
```json
{
  "completed": false
}
```

---

### 5. Required `project_id`
**Change:** The `project_id` is now a required field when creating a task.

**Before:**
```json
{
  "title": "New task title"
}
```

**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Envelope
**Change:** List endpoints now return a paginated envelope rather than a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API endpoints to use the `/v2/` prefix.
2. Change the authentication header to use `Authorization: Bearer <your_api_token>`.
3. Change all instances of `id` from integer to UUID string in Task objects.
4. Rename all references of `done` to `completed` in the Task object.
5. Ensure `project_id` is provided in the task creation request.
6. Update list requests to handle the new paginated response.

## Upgrade Command

To upgrade to v2, run the following command:
```bash
zrb upgrade
```