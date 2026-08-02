# Migration Guide from Zrb v1 to v2

## Overview
This guide provides a clear migration path for experienced developers upgrading from Zrb v1 to v2. It outlines all breaking changes, along with code examples to assist in the transition.

## Breaking Changes

### 1. Endpoint Prefix
**Change:** All endpoints are now prefixed with `/v2/`.
#### Before:
```plaintext
GET /tasks
```
#### After:
```plaintext
GET /v2/tasks
```

### 2. Authentication Header
**Change:** The authentication header has changed from `X-Auth-Token` to a Bearer token.
#### Before:
```plaintext
X-Auth-Token: <your_api_key>
```
#### After:
```plaintext
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Change:** The type of the `id` field in the Task object has changed from an integer to a UUID string.
#### Before:
```json
{
  "id": 42,
  "title": "Write tests"
}
```
#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Task Field Renaming
**Change:** The field `done` has been renamed to `completed` in the Task object.
#### Before:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```
#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

### 5. Required Field for Task Creation
**Change:** The creation of a task now requires a `project_id` field.
#### Before:
```json
{
  "title": "New task title"
}
```
#### After:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Response
**Change:** All list endpoints now return a paginated envelope instead of a bare array.
#### Before:
```json
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
#### After:
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
1. Update API endpoint paths to include `/v2/`.
2. Change the authentication header to use Bearer token.
3. Update any task `id` handling to expect UUID strings.
4. Rename `done` to `completed` in task objects.
5. Ensure `project_id` is included in task creation requests.
6. Adapt to the new paginated list response format.

## Upgrade Command
After reviewing all changes, run the following upgrade command:
```sh
yarn upgrade zrb@2.0.0
```
