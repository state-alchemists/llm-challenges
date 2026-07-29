# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide provides a comprehensive overview of the changes between v1 and v2 of the Zrb CLI API. It aims to facilitate a smooth transition for developers familiar with v1 by outlining all breaking changes and providing code examples.

## Breaking Changes

### 1. Endpoint Prefix Change
All endpoints are now prefixed with `/v2/`.  
**Before:**  
```
GET /tasks
```
**After:**  
```
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication header format has changed from `X-Auth-Token` to a Bearer token format.  
**Before:**  
```
X-Auth-Token: <your_api_key>
```
**After:**  
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
The `id` field type for tasks has changed from an integer to a UUID string.  
**Before:**  
```json
{
  "id": 42,
  "title": "Write tests"
}
```  
**After:**  
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Task Field Renaming
The `done` field has been renamed to `completed`.  
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

### 5. Required Project ID for Task Creation
Creating a task now requires a `project_id` field in the request body.  
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

### 6. Paginated Response for List Endpoints
List endpoints now return a paginated envelope instead of a bare array.  
**Before:**  
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```  
**After:**  
```json
{
  "items": [
    {"id": "1", "title": "Buy milk", "completed": false},
    {"id": "2", "title": "Ship v2", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update API endpoints to include the `/v2/` prefix.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update task ID handling from integer to UUID string format.
4. Rename the `done` field to `completed` in task objects.
5. Ensure all task creation requests include the `project_id` field.
6. Adapt to the new paginated response structure when retrieving task lists.

## Upgrade Command
To upgrade to v2, use the following command:
```bash
zrb upgrade v2
```

Ensure that all changes are fully tested before deploying the new version.