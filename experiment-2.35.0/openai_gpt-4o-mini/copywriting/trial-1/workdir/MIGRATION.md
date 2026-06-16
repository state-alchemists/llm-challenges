# Migration Guide: Zrb CLI v1 to v2

## Introduction
This guide outlines the breaking changes from v1 to v2 of the Zrb CLI. It provides a clear structure to help you with the migration process, including code examples and a checklist at the end.

## Breaking Changes

### 1. Endpoint Prefix Change
All API endpoints are now prefixed with `/v2/`.

**Before:**
```
GET /tasks
```
**After:**
```
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```
X-Auth-Token: <your_api_key>
```
**After:**
```
Authorization: Bearer <your_api_token>
```
Requests with the old header will receive HTTP 401.

### 3. Task ID Type Change
The type of `id` for tasks has changed from an integer to a UUID string.

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

### 4. Field Renaming: `done` to `completed`
The field `done` has been renamed to `completed` in the task object.

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

### 5. Required Field: `project_id`
Task creation now requires a `project_id`.

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
Omitting `project_id` will return HTTP 422.

### 6. Paginated Responses
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
    {"id": "2", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all endpoint URLs to include the `/v2/` prefix.
2. Change authentication header from `X-Auth-Token` to Bearer token.
3. Change `id` fields for tasks from integer to UUID strings.
4. Rename `done` field to `completed` in all task objects.
5. Ensure `project_id` is included in all task creation requests.
6. Update code to handle paginated responses from list endpoints.

## Upgrade Command
To upgrade to version 2 of the Zrb CLI, use the following command:
```bash
npm install zrb@latest
```