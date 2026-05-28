# Migration Guide from Zrb v1 to v2

This guide provides instructions for migrating your Zrb API integration from version 1 (v1) to version 2 (v2). The new version introduces breaking changes, improved functionality, and stricter authentication. Please read carefully to ensure a smooth transition.

## Breaking Changes

### 1. Endpoint Versioning
**Change**: All endpoints are now prefixed with `/v2/`.  
**Before**:
```http
GET /tasks
```
**After**:
```http
GET /v2/tasks
```

### 2. Authentication Header
**Change**: The authentication header has changed from `X-Auth-Token` to a Bearer token.  
**Before**:
```http
X-Auth-Token: <your_api_key>
```
**After**:
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Change**: The type of the task `id` has changed from an integer to a UUID string.  
**Before**:
```json
{id: 42}
```
**After**:
```json
{id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

### 4. Renamed Task Field
**Change**: The task field `done` is now `completed`.  
**Before**:
```json
{"done": false}
```
**After**:
```json
{"completed": false}
```

### 5. Required Project ID on Task Creation
**Change**: Task creation now requires a `project_id` field.  
**Before**:
```json
{
  "title": "New task title"
}
```
**After**:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Response for List Endpoints
**Change**: List endpoints return a paginated envelope instead of a bare array.  
**Before**:
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```
**After**:
```json
{
  "items": [
    {"id": "1", "title": "Buy milk", "completed": false},
    {"id": "2", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

1. Update your API calls to use the new `/v2/` prefixed endpoints.
2. Replace authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Adjust your data structures to accommodate the change of `id` type to UUID strings.
4. Rename any usage of the `done` field to `completed`.
5. Ensure that you include `project_id` when creating tasks.
6. Update list handling to work with the new paginated response format.

## Upgrade Command

To upgrade the Zrb CLI to version 2, run:
```bash
zrb upgrade
```