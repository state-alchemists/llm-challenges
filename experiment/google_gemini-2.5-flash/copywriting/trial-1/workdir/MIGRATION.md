# Zrb CLI v1 to v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides step-by-step instructions for migrating your existing v1 integrations.

## Introduction to v2

Zrb CLI v2 introduces significant enhancements, including support for projects, improved pagination, and a more secure authentication mechanism. These changes require updates to your existing API calls.

## Breaking Changes

### 1. All Endpoints are now prefixed with `/v2/`

All API routes have been updated to include a `/v2/` prefix.

**Before (v1):**
```
GET /tasks
POST /tasks
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
```

### 2. Authentication Header Changed

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`. Requests using the old header will result in an HTTP 401 Unauthorized error.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects is now a UUID string instead of an integer. This affects all endpoints that accept or return a task ID.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  ""title": "Old task",
  "done": false
}
```
**Before (v1) - Get Task:**
```
GET /tasks/42
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New task",
  "completed": false,
  "project_id": "proj_abc123"
}
```
**After (v2) - Get Task:**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. This affects both the Task object structure and requests for updating task status.

**Before (v1) - Task Object:**
```json
{
  "id": 1,
  "title": "Finish report",
  "done": false
}
```
**Before (v1) - Update Task:**
```json
{
  "done": true
}
```

**After (v2) - Task Object:**
```json
{
  "id": "...",
  "title": "Finish report",
  "completed": false,
  "project_id": "..."
}
```
**After (v2) - Update Task:**
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) - Create Task:**
```json
{
  "title": "New task title"
}
```

**After (v2) - Create Task:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response envelope instead of a bare array of task objects. This envelope includes `items`, `total`, and `next_cursor` fields.

**Before (v1) - List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - List Tasks Response:**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, append `?cursor=<next_cursor>` to your request.

## Migration Checklist

1.  [ ] Update all API endpoint paths to include the `/v2/` prefix.
2.  [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer`.
3.  [ ] Adapt your code to handle UUID strings for task IDs instead of integers.
4.  [ ] Rename all references to the `done` field to `completed`.
5.  [ ] Ensure all task creation requests include a valid `project_id` in the request body.
6.  [ ] Update code that processes list endpoint responses to handle the new paginated envelope structure.

## Upgrade Command

To upgrade your Zrb CLI to v2, run:

```bash
zrb upgrade --version 2
```
