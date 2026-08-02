# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication. Please review all breaking changes carefully before upgrading.

## What's New in v2

v2 introduces projects, improved pagination, and stricter auth. Several v1 fields and conventions have changed to provide a more robust and scalable API.

## Breaking Changes

### 1. Endpoint Prefix

All API endpoints are now prefixed with `/v2/`. You must update all your API request paths to include this new prefix.

**Before (v1):**
```
GET /tasks
POST /tasks
GET /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

### 2. Authentication Header

The authentication mechanism has been updated. The `X-Auth-Token` header is no longer supported. All requests must now use a Bearer token in the `Authorization` header.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will result in an HTTP 401 Unauthorized error.

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference tasks by their ID.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests"
}
```
**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

When fetching, updating, or deleting tasks, ensure you are passing a UUID string for the `id`.

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. You must update your code to use the new field name when reading or updating task objects.

**Before (v1):**
```json
{
  "title": "Ship v1",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Ship v1",
  "completed": true
}
```

### 5. Task Creation Requires `project_id`

When creating new tasks, the `project_id` field is now mandatory. This allows tasks to be organized within specific projects. Omitting `project_id` will result in an HTTP 422 Unprocessable Entity error.

**Before (v1):**
```
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
```
POST /v2/tasks
Content-Type: application/json
Authorization: Bearer <your_api_token>

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints, such as `GET /v2/tasks`, now return a paginated envelope object instead of a bare array of items. This new structure includes metadata like `total` and `next_cursor` for easier pagination handling.

**Before (v1):**
```
GET /tasks

[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```
GET /v2/tasks
Authorization: Bearer <your_api_token>

{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_xyz", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v1", "completed": true, "project_id": "proj_xyz", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, use the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

## Migration Checklist

1.  [ ] **Update CLI to v2:** Run the upgrade command to install Zrb CLI v2.
2.  [ ] **Review Authentication:** Update all API clients to use `Authorization: Bearer <your_api_token>` header.
3.  [ ] **Adjust Endpoint Paths:** Prefix all Zrb API endpoint calls with `/v2/`.
4.  [ ] **Handle Task IDs:** Update any code that stores or uses task IDs to expect UUID strings instead of integers.
5.  [ ] **Rename Task Field:** Change all references from `task.done` to `task.completed`.
6.  [ ] **Provide `project_id` for New Tasks:** Ensure all task creation requests include a `project_id`.
7.  [ ] **Update List Parsing:** Modify code that consumes list endpoint responses to handle the new paginated envelope structure (access items via `response.items`).
8.  [ ] **Implement Pagination:** Adopt the new `cursor`-based pagination for list endpoints.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 release, run:

```bash
zrb upgrade --version 2
```
