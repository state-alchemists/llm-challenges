# Migration Guide from Zrb v1 to v2

## Overview
This guide provides a comprehensive overview of the breaking changes between Zrb v1 and v2, along with migration steps and examples for developers already familiar with v1.

## Breaking Changes

### 1. API Versioning
**Change:** All endpoints are now prefixed with `/v2/`.

#### Before:
```
GET /tasks
```
#### After:
```
GET /v2/tasks
```

### 2. Authentication Header
**Change:** The authentication header has changed from `X-Auth-Token` to a Bearer token.

#### Before:
```
X-Auth-Token: <your_api_key>
```
#### After:
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Change:** The type of the `id` field for tasks has changed from an integer to a UUID string.

#### Before:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Task Field Rename
**Change:** The field `done` has been renamed to `completed`.

#### Before:
```json
{
  "title": "Updated title",
  "done": true
}
```
#### After:
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Required Field for Task Creation
**Change:** When creating a task, the `project_id` field is now required.

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

### 6. Pagination in List Responses
**Change:** List endpoints now return a paginated envelope instead of a bare array.

#### Before:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
#### After:
```json
{
  "items": [
    {"id": "a1b2c3d4", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "a1b2c3d5", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API endpoint URLs to include `/v2/`.
2. Change the authentication method to use Bearer tokens.
3. Modify any code that creates or updates tasks to adapt to the new `id` type (UUID string instead of integer).
4. Rename `done` to `completed` wherever applicable in your codebase.
5. Ensure `project_id` is included when creating tasks.
6. Update code handling responses from list endpoints to manage the paginated structure.

## Upgrade Command
To upgrade the CLI to version 2, execute:
```
npm install zrb@latest
```