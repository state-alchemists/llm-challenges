# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 introduces significant enhancements, including project management capabilities, improved API consistency, and more robust authentication. This guide will walk you through the necessary changes to migrate your existing v1 integrations to v2.

## Breaking Changes

Below is a detailed breakdown of every breaking change, including before-and-after code examples to facilitate your migration.

### 1. All Endpoints Now Use a `/v2/` Prefix

All API endpoints have been moved under the `/v2/` path prefix to clearly delineate between API versions.

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

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported.

**Before (v1):**
Requests used `X-Auth-Token`.
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
Authentication now uses a standard Bearer token in the `Authorization` header.
```
Authorization: Bearer <your_api_token>
```
Requests using the old `X-Auth-Token` will receive an HTTP 401 Unauthorized response.

### 3. Task `id` Type Changed to UUID String

The `id` field for task objects has changed from an integer to a UUID string. This affects all endpoints that reference a task by its ID.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```
Accessing a task:
```
GET /tasks/42
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```
Accessing a task:
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed for clarity.

**Before (v1):**
```json
{
  "title": "Update documentation",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Update documentation",
  "completed": true
}
```
When updating a task, ensure you use the `completed` field.

### 5. Task Creation Now Requires `project_id`

In v2, all tasks must belong to a project. A `project_id` is now a mandatory field when creating a new task.

**Before (v1):**
```
POST /tasks
```
Request body:
```json
{
  "title": "Organize meeting notes"
}
```

**After (v2):**
```
POST /v2/tasks
```
Request body:
```json
{
  "title": "Organize meeting notes",
  "project_id": "proj_xyz456"
}
```
Omitting `project_id` during task creation will result in an HTTP 422 Unprocessable Entity error.

### 6. List Endpoints Return a Paginated Envelope

List endpoints (e.g., `GET /tasks`) no longer return a bare array of items. Instead, they return a paginated envelope object that includes metadata for easier navigation.

**Before (v1):**
```
GET /tasks
```
Response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2):**
```
GET /v2/tasks
```
Response:
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "..."},
    {"id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page of results, include the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`. You can also specify `limit` for results per page.

## Migration Checklist

Follow these steps to migrate your Zrb CLI integrations to v2:

1.  **Update Endpoint Paths**: Prefix all Zrb API calls with `/v2/`.
2.  **Change Authentication**:
    *   Switch from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
    *   Ensure your API key is properly formatted as a Bearer token.
3.  **Adjust Task ID Handling**:
    *   Update your code to expect and use UUID strings for task IDs instead of integers.
    *   If you store task IDs, you may need to migrate existing integer IDs to UUIDs.
4.  **Rename `done` to `completed`**:
    *   Replace all occurrences of the `done` field with `completed` in your request bodies and when processing task objects.
5.  **Provide `project_id` for Task Creation**:
    *   Ensure that every `POST /v2/tasks` request includes a valid `project_id` in its request body.
6.  **Handle Paginated Responses**:
    *   Modify your logic for listing tasks to parse the new paginated envelope structure (e.g., access `response.items`).
    *   Implement pagination logic using `next_cursor` and `cursor` query parameters if you require fetching multiple pages.

## Upgrade Command

To upgrade your Zrb CLI installation, run:

```bash
zrb upgrade --version v2
```
