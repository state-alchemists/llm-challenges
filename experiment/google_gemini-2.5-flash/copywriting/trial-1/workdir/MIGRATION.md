# Zrb CLI v1 to v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides a step-by-step process to migrate your applications from v1 to v2. Version 2 brings significant enhancements, including project management, improved pagination, and a more robust authentication mechanism.

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints (without `/v2/`) will no longer work.

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

The authentication header has changed from `X-Auth-Token` to an `Authorization` Bearer token. Requests using `X-Auth-Token` will result in an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Changed

The `id` field for Task objects has changed from an integer to a UUID string.

**Before (v1) Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2) Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`.

**Before (v1) Update Task Request:**
```json
{
  "done": true
}
```

**After (v2) Update Task Request:**
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) Create Task Request:**
```json
{
  "title": "New task title"
}
```

**After (v2) Create Task Request:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of task objects. This envelope includes `items`, `total`, and `next_cursor` fields for pagination.

**Before (v1) List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) List Tasks Response:**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_1", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v1", "completed": true, "project_id": "proj_1", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, use the `cursor` query parameter:

```
GET /v2/tasks?cursor=cursor_xyz
```

## Migration Checklist

1.  **Update CLI:** Upgrade your Zrb CLI to version 2.
2.  **API Endpoints:** Prefix all your API requests with `/v2/`.
3.  **Authentication:** Change your authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
4.  **Task IDs:** Update your code to handle task `id`s as UUID strings instead of integers.
5.  **Task Status Field:** Rename all occurrences of the `done` field to `completed` in your Task object representations and API request bodies.
6.  **Task Creation:** Ensure all task creation requests (`POST /v2/tasks`) include the required `project_id` in the request body.
7.  **List Endpoint Responses:** Adapt your code to parse paginated responses from list endpoints. Access task items from the `items` array within the response envelope.

## Upgrade Command

To upgrade your Zrb CLI to v2, run:

```bash
npm install -g zrb@latest
# or, if using pip:
pip install --upgrade zrb
```

*Note: Replace `npm` or `pip` with your specific package manager if it differs.*
