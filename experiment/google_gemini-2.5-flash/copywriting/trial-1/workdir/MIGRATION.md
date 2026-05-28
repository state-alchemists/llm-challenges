# Zrb Task API v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your applications from Zrb Task API v1 to v2. Version 2 introduces significant improvements, including project support, enhanced authentication, and consistent pagination, alongside several breaking changes.

## Breaking Changes

### 1. All Endpoints are Now Prefixed with `/v2/`

All API endpoints now require `/v2/` as a prefix. This change ensures versioning consistency and allows for future API evolution without impacting older versions.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication Header Changed

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is deprecated and replaced by a standard `Authorization: Bearer` token. Requests using the old header will result in an HTTP 401 Unauthorized error.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects has been updated from an integer to a UUID string. This provides greater flexibility and uniqueness for task identifiers.

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

When fetching or updating a task by ID, ensure you pass a UUID string instead of an integer.

**Before (v1 - Get Task):**
```
GET /tasks/42
```

**After (v2 - Get Task):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1 - Update Task):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 - Update Task):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

In v2, tasks are associated with projects. When creating a new task, you must now include a `project_id` in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1 - Create Task):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Create Task):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints, such as `GET /v2/tasks`, now return a paginated envelope object instead of a bare array of items. This new structure includes metadata like total item count and a `next_cursor` for efficient pagination.

**Before (v1 - List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 - List Tasks Response):**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the `next_cursor` as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`. You can also control the page size using `limit`.

## Migration Checklist

1.  **Update Endpoint Paths:** Change all API endpoint calls to include the `/v2/` prefix.
2.  **Modify Authentication:** Switch from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling:** Update your code to expect and use UUID strings for task IDs instead of integers.
4.  **Rename `done` to `completed`:** Change all references to the task completion field from `done` to `completed`.
5.  **Provide `project_id` for New Tasks:** Ensure all task creation requests include a `project_id` in the request body.
6.  **Adapt to Paginated Responses:** Update your code to parse the new paginated envelope structure for list endpoints, accessing items via the `items` array and handling `next_cursor` for pagination.

## Upgrade Command

To ensure you have the latest Zrb CLI client (if applicable), run:

```bash
pip install zrb --upgrade
```
