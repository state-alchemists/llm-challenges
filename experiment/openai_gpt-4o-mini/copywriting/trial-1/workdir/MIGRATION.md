# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide provides a comprehensive overview of breaking changes from v1 to v2 of the Zrb CLI. Developers using v1 are encouraged to follow the steps outlined below to successfully transition to the new version.

## Breaking Changes
Below is a detailed list of the breaking changes introduced in v2:

### 1. Endpoint Prefix Change
All endpoints are now prefixed with `/v2/`.

**Before:**
```plaintext
GET /tasks
```
**After:**
```plaintext
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication header has been modified from `X-Auth-Token` to a Bearer token.

**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```
**After:**
```plaintext
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
The `id` field in the Task object has changed from an integer to a UUID string.

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
The `done` field has been renamed to `completed` in the Task object.

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

### 5. Required Field Addition for Task Creation
When creating a task, the `project_id` is now a required field.

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

### 6. Paginated Responses
List endpoints now return a paginated envelope instead of a bare array.

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
1. Update all API calls to use the `/v2/` prefix.
2. Change the authentication header format to use Bearer token.
3. Replace integer `id` fields with UUID strings in Task objects.
4. Rename all instances of `done` to `completed` in Task objects.
5. Include the `project_id` in all Task creation requests.
6. Adapt to handle paginated responses from list endpoints.

## Upgrade Command
To upgrade your Zrb CLI to the latest version, run:
```bash
zrb upgrade
```