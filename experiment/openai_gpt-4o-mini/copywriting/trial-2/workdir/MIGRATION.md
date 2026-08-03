# Zrb Task API Migration Guide from v1 to v2

## Overview
This guide outlines the breaking changes introduced in v2 of the Zrb Task API and how to migrate from v1 to v2. Follow the steps and examples to ensure a smooth transition.

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
**Change:** The authentication header changed from `X-Auth-Token` to `Authorization: Bearer`.

**Before:**
```http
X-Auth-Token: <your_api_key>
```

**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
**Change:** The `id` field in the Task object changed its type from integer to UUID string.

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
**Change:** The field `done` has been renamed to `completed` in the Task object.

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

### 5. Project ID Requirement
**Change:** Creating a task now requires the `project_id` field to be present.

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

### 6. List Endpoints Response Change
**Change:** The response format for list endpoints now includes a paginated envelope instead of a bare array.

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
  "items": [
    {"id": "1", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "2", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update your endpoint URLs from `/tasks` to `/v2/tasks`.
2. Change the authentication header to use `Authorization: Bearer <your_api_token>`.
3. Update your task ID handling to support UUIDs.
4. Rename any `done` references in your Task objects to `completed`.
5. Ensure all task creation requests include a `project_id`.
6. Adapt your handling of list responses to account for the new paginated structure.

## Upgrade Command
Run the following command to upgrade:
```bash
zrb upgrade
```