# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides a step-by-step process to migrate your applications from v1. The new version introduces projects, improved pagination, and stricter authentication.

## Breaking Changes

### 1. API Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. You must update your API request paths accordingly.

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

### 2. Authentication Header Update

The authentication header has changed from `X-Auth-Token` to a standard `Authorization: Bearer` token. Requests using the old header will receive an HTTP 401 Unauthorized response.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference tasks by ID.

**Before (v1 - Task object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
**After (v2 - Task object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1 - Get Task):**
```
GET /tasks/42
```

**After (v2 - Get Task):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. This affects task creation and update operations, as well as the structure of returned Task objects.

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

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

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

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response object instead of a bare array of items. The actual task objects are nested under the `items` key. Pagination can be controlled with `cursor` and `limit` query parameters.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "e6f7g8h9-...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

1.  **Update CLI Installation:** Upgrade your Zrb CLI to the latest v2 release.
2.  **Adjust Endpoint Paths:** Prefix all your API requests with `/v2/`.
3.  **Refactor Authentication:** Change your `X-Auth-Token` header to `Authorization: Bearer <your_api_token>`.
4.  **Update Task ID Handling:** Modify your code to expect and use UUID strings for task `id`s instead of integers.
5.  **Rename `done` Field:** Replace all instances of the `done` field with `completed` in your task objects and API requests.
6.  **Add `project_id` to Task Creation:** Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
7.  **Adapt List Endpoint Responses:** Update your code to parse paginated responses from list endpoints, accessing task data via the `items` array.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run:

```bash
zrb upgrade --version 2
```
