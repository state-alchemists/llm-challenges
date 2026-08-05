# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide is designed for experienced developers who are currently using version 1 (v1) of the Zrb CLI and need to transition to version 2 (v2). This guide covers all breaking changes, along with examples and a checklist to ensure a smooth migration.

## Breaking Changes

### 1. Endpoint Prefix Change
All API endpoints are now prefixed with `/v2/`.

**Before:**  
`GET /tasks`  
**After:**  
`GET /v2/tasks`

### 2. Authentication Header Change
The authentication method has changed from using `X-Auth-Token` to using a Bearer token in the `Authorization` header.

**Before:**
```
X-Auth-Token: <your_api_key>
```
**After:**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
The `id` field in the task object has changed from an integer to a UUID string.

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
The `done` field in the task object has been renamed to `completed`.

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

### 5. Required Project ID in Task Creation
The creation of a task now requires the `project_id` field.

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

### 6. Paginated List Responses
List endpoints now return a paginated envelope containing the tasks, rather than a bare array.

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
    {"id": "1", "title": "Buy milk"},
    {"id": "2", "title": "Ship v1"}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```


## Migration Checklist
1. Update all API endpoint URLs to include `/v2/`.
2. Change authentication from `X-Auth-Token` to Bearer token in the `Authorization` header.
3. Update data types for `id` fields from integers to UUID strings.
4. Replace all instances of `done` with `completed`.
5. Ensure that `project_id` is included in all task creation requests.
6. Adapt the handling of list responses to manage paginated data.

## Upgrade Command
To upgrade to version 2 of the Zrb CLI, run the following command:
```
npm install zrb-cli@2.0.0
```