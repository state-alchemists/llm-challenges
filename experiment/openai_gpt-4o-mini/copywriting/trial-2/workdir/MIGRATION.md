# Zrb CLI Migration Guide from v1 to v2

This guide provides a structured overview of the breaking changes introduced in v2 of the Zrb CLI Task API comparing with version 1. Follow the steps outlined here for a successful migration.

---

## Breaking Changes

### 1. Endpoint Prefix Change

**Change:** All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change

**Change:** Authentication header changed from `X-Auth-Token` to Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

**Change:** Task `id` type changed from integer to UUID string.

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

### 4. Task Field Renaming

**Change:** Task field `done` is renamed to `completed`.

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

### 5. Project ID Requirement on Task Creation

**Change:** Task creation now requires `project_id`.

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

### 6. Updated List Endpoint Response Format

**Change:** List endpoints now return a paginated envelope instead of a bare array.

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

---

## Migration Checklist
1. Update all API requests to use the `/v2/` prefix.
2. Change authentication header to use Bearer tokens.
3. Update task ID handling to use UUID strings instead of integers.
4. Rename any references to the `done` field to `completed`.
5. Ensure `project_id` is included in all task creation requests.
6. Update any list request handling to account for the paginated response format.

---

## Upgrade Command

Run the following command to upgrade your Zrb CLI to version 2:
```bash
zrb upgrade
```