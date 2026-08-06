# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide provides a clear structure for developers migrating from v1 to v2 of the Zrb CLI. It highlights all breaking changes, provides code examples, and includes a migration checklist to ensure a smooth transition.

## Breaking Changes

### 1. Endpoint Prefix Change
**Breaking Change:** All API endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
**Breaking Change:** The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
**Breaking Change:** The `id` of the task has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```
**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

### 4. `done` Field Renamed to `completed`
**Breaking Change:** The `done` field has been renamed to `completed` in task objects.

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

### 5. Project ID Required for Task Creation
**Breaking Change:** Creating a task now requires a `project_id`.

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

### 6. Paginated List Response
**Breaking Change:** List endpoints now return a paginated envelope rather than a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
**After:**
```json
{
  "items": [
    {"id": 1, "title": "Buy milk"},
    {"id": 2, "title": "Ship v1"}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update the API endpoint prefix from `/tasks` to `/v2/tasks`.
2. Change the authentication header to use Bearer token.
3. Update the task object `id` field from integer to UUID string.
4. Rename the `done` field in tasks to `completed`.
5. Modify the task creation request to include `project_id`.
6. Update code that handles task list responses to accommodate the new paginated format.

## Upgrade Command
Run the following command to upgrade to v2:
```bash
zrb upgrade
```