# Zrb CLI Migration Guide from v1 to v2

## Introduction
This guide is intended for developers migrating from v1 to v2 of the Zrb CLI. Version 2 introduces breaking changes that require code updates to ensure compatibility.

## Breaking Changes

### 1. Endpoint Prefix Change
The base path for all API requests has changed. All previous endpoints now require a `/v2/` prefix.

**Before:**
```plaintext
GET /tasks
```

**After:**
```plaintext
GET /v2/tasks
```

### 2. Authentication Header Change
The method of authentication has shifted from using `X-Auth-Token` to a Bearer token in the `Authorization` header.

**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```

**After:**
```plaintext
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
The `id` field of the Task object has changed from an integer to a UUID string.

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

### 4. Field Renaming
The `done` field has been renamed to `completed`. Ensure to update your code to reflect this change.

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

### 5. Required Field for Task Creation
Creating a task now requires the `project_id` field in the request body; omitting it will return an HTTP 422 error.

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

### 6. Pagination in List Endpoints
The responses from list endpoints now return a paginated envelope rather than a bare array of tasks. This includes a `next_cursor` for fetching additional pages.

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
1. Update all API request paths to include `/v2/`.
2. Change the authentication header to use Bearer tokens.
3. Modify your code to handle UUIDs for task IDs.
4. Rename all occurrences of the `done` field to `completed`.
5. Ensure that the `project_id` is included in all task creation requests.
6. Update your handling of list responses to accommodate pagination.

## Upgrade Command
To upgrade to v2, run:
```bash
npm install zrb@latest
```