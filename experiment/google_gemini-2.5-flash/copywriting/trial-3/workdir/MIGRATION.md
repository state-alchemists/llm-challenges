# Zrb CLI v2 Migration Guide

## Introduction

This guide outlines the necessary steps and considerations for migrating your existing Zrb CLI v1 integrations to the new Zrb CLI v2 API. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, along with several breaking changes.

## Breaking Changes

Here's a detailed breakdown of every breaking change in Zrb CLI v2, along with before and after code examples.

### 1. All Endpoints Are Now Prefixed with `/v2/`

All API endpoints have been moved under the `/v2/` path prefix. Requests to v1 endpoints will no longer be routed correctly.

**Before (v1):**
```http
GET /tasks
```

**After (v2):**
```http
GET /v2/tasks
```

### 2. Authentication Header Changed

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header. Requests using `X-Auth-Token` will now result in an HTTP 401 Unauthorized error.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects, previously an integer, is now a UUID string. This change affects all endpoints that involve specifying a task ID, such as `GET /tasks/{id}`, `PUT /tasks/{id}`, and `DELETE /tasks/{id}`.

**Before (v1 - Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 - Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1 - Get Task example):**
```http
GET /tasks/42
X-Auth-Token: <your_api_key>
```

**After (v2 - Get Task example):**
```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer <your_api_token>
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. This affects both the Task object structure and the request body for updating tasks.

**Before (v1 - Update Task request body):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 - Update Task request body):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

When creating new tasks, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1 - Create Task request body):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Create Task request body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope Instead of a Bare Array

All list endpoints, such as `GET /v2/tasks`, now return a paginated envelope object instead of a bare array of items. This envelope includes the `items` array, `total` count, and a `next_cursor` for pagination.

**Before (v1 - List Tasks response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 - List Tasks response):**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, include the `cursor` query parameter:

```http
GET /v2/tasks?cursor=cursor_xyz
```

## Migration Checklist

Follow these steps to migrate your Zrb CLI v1 integration to v2:

1.  **Update API Endpoints**: Change all API request paths to include the `/v2/` prefix.
2.  **Adjust Authentication**: Modify your authentication mechanism to use the `Authorization: Bearer <your_api_token>` header instead of `X-Auth-Token`.
3.  **Handle Task ID Type**: Update your code to expect and handle UUID strings for task `id`s instead of integers. This includes parsing responses and constructing requests.
4.  **Rename `done` to `completed`**: Change all references to the `done` field in task objects and update request bodies for task updates to use `completed`.
5.  **Add `project_id` to Task Creation**: Ensure all task creation requests include a valid `project_id` in the request body.
6.  **Update List Endpoint Parsing**: Modify your code to parse the new paginated envelope structure for list responses, accessing task items via the `items` array and handling `next_cursor` for pagination.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run the following command:

```bash
npm install -g zrb-cli@latest
```
