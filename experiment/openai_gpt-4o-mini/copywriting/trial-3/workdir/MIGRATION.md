# Migration Guide from Zrb v1 to v2

## Overview
This guide outlines the breaking changes between Zrb v1 and v2, along with examples and a step-by-step migration checklist for experienced developers already using v1.

## Breaking Changes

### 1. Endpoint Prefix
**Change:** All endpoints are now prefixed with `/v2/`.  
**Before:** `GET /tasks`  
**After:** `GET /v2/tasks`

### 2. Authentication Header
**Change:** The authentication header has changed from `X-Auth-Token` to Bearer token.  
**Before:**  
```
X-Auth-Token: <your_api_key>
```
**After:**  
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Change:** The `id` type of task objects has changed from integer to UUID string.  
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
**Change:** The `done` field has been renamed to `completed`.  
**Before:**  
```json
{
  "title": "Updated title",
  "done": true
}
```  
**After:**  
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Required Project ID for Task Creation
**Change:** The creation of a task now requires a `project_id`.  
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

### 6. Paginated List Envelope
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

## Migration Checklist
1. Update all endpoint URLs from `/tasks` to `/v2/tasks`.
2. Change the authentication header to `Authorization: Bearer <your_api_token>`.
3. Change task id usage from integer to UUID string format.
4. Rename the `done` field to `completed` in all requests and responses.
5. Ensure `project_id` is included in task creation requests.
6. Adjust the handling of list responses to accommodate pagination.

## Upgrade Command
To upgrade to Zrb v2, run:
```
npm install zrb@latest
```