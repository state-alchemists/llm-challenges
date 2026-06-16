# Zrb CLI Migration Guide from v1 to v2

## Introduction
This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers practical examples for migrating existing applications from v1.

## Breaking Changes Overview
The following are the notable breaking changes from v1 to v2:

1. **Endpoint Prefix Change**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header Change**: The authentication mechanism has changed from an API key to a Bearer token.
3. **Task ID Type Change**: The `id` field in the Task object has changed from an integer to a UUID string.
4. **Task Field Rename**: The `done` field in the Task object has been renamed to `completed`.
5. **Project Requirement in Task Creation**: Task creation now requires a `project_id` field.
6. **Paginated List Responses**: List endpoints now return a paginated envelope rather than a bare array.

## Breaking Change Details
### 1. Endpoint Prefix Change
**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```
Requests with the old header will result in a `401 Unauthorized` response.

### 3. Task ID Type Change
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

### 4. Task Field Rename
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

### 5. Project Requirement for Task Creation
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
Omitting `project_id` will return a `422 Unprocessable Entity` response.

### 6. Paginated List Responses
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
    {"id": "...", "title": "Buy milk", "completed": false},
    {"id": "...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update your API endpoint URLs to include the `/v2/` prefix.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Adjust your code to handle `id` as a UUID string instead of an integer.
4. Rename any references to `done` to `completed` in your Task objects.
5. Ensure that all Task creation requests include a `project_id`.
6. Adapt your client logic to handle paginated list responses.

## Upgrade Command
Finally, upgrade your Zrb CLI with the following command:
```bash
zrb upgrade
```