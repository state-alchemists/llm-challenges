# Migration Guide from Zrb v1 to v2

## Introduction
This migration guide is intended for developers who are currently using the Zrb v1 API and need to upgrade to v2. The Zrb v2 API introduces breaking changes, new features, and improved standards for authentication and data structures.

## Breaking Changes

### 1. Endpoint Prefix Change
All API endpoints are now prefixed with `/v2/`.

**Before:**  
`GET /tasks`  
**After:**  
`GET /v2/tasks`

### 2. Authentication Header Change
The authentication method has changed from using an API key in the header to using a Bearer token.

**Before:**  
```plaintext
X-Auth-Token: <your_api_key>
```  
**After:**  
```plaintext
Authorization: Bearer <your_api_token>
```

Requests that still use `X-Auth-Token` will receive an HTTP 401 response.

### 3. Task ID Type Change
The `id` type of the Task object has changed from an integer to a UUID string.

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

### 4. Field Rename: `done` to `completed`
The field `done` in the Task object has been renamed to `completed`.

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

### 5. Required Field Addition: `project_id`
When creating a Task, `project_id` is now a required field.

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
Omitting `project_id` will return an HTTP 422 response.

### 6. Response Structure Change for List Endpoints
List endpoints now return a paginated envelope instead of a plain array. 

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
To fetch the next page, use `?cursor=<next_cursor>` in your requests.

## Migration Checklist
1. Update all endpoint URLs to include `/v2/` prefix.
2. Replace the authentication header `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
3. Change the `id` type from integer to UUID string in your Task object.
4. Rename the field `done` to `completed` in Task objects.
5. Ensure `project_id` is included in task creation requests.
6. Adjust to handle paginated responses from list endpoints.

## Upgrade Command  
To upgrade to the latest version of Zrb, run:
```bash
zrb upgrade
```