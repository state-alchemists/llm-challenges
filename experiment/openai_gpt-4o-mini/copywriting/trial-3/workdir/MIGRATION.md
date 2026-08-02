# Zrb CLI Migration Guide: v1 to v2

## Overview
This guide provides steps for migrating from v1 to v2 of the Zrb CLI. The new version comes with significant changes that require adjustments in your implementation. Below, we outline each breaking change and provide code examples to aid in your transition.

## Breaking Changes

### 1. Endpoint Prefix Change
**Before:** v1 endpoints are as follows:
```plaintext
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```
**After:** v2 endpoints now include a `/v2/` prefix:
```plaintext
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication Header Change
**Before:** Use the following header in v1 requests:
```plaintext
X-Auth-Token: <your_api_key>
```
**After:** In v2, use Bearer token:
```plaintext
Authorization: Bearer <your_api_token>
```

### 3. Change in Task ID Type
**Before:** The task `id` was an integer:
```json
{
  "id": 42,
  "title": "Write tests"
}
```
**After:** In v2, the `id` is a UUID string:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Field Renaming: `done` to `completed`
**Before:** The field was named `done`:
```json
{
  "done": false
}
```
**After:** It has been renamed to `completed`:
```json
{
  "completed": false
}
```

### 5. New Requirement: `project_id` for Task Creation
**Before:** Task creation did not require a `project_id`:
```json
{
  "title": "New task title"
}
```
**After:** Now `project_id` is required:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Response for List Tasks
**Before:** List tasks returned a bare array:
```json
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
**After:** v2 responds with a paginated envelope:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update API endpoint prefixes from `/tasks` to `/v2/tasks`.
2. Change authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update task `id` from integer to UUID string in your code.
4. Rename task field `done` to `completed` throughout your code.
5. Ensure that task creation includes the required `project_id`.
6. Update any code handling responses from list tasks to accommodate the new paginated structure.

## Upgrade Command
To upgrade to v2, run the following command:
```bash
zrb upgrade --version 2
```  
