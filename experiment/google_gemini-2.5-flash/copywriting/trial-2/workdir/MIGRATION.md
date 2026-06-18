# Zrb CLI v1 to v2 Migration Guide

This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers clear instructions to help you migrate your existing v1 implementations. Zrb CLI v2 brings significant improvements, including project support, enhanced authentication, and more robust API responses.

## Summary of Breaking Changes

1.  **Endpoint Prefix:** All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header:** The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`.
3.  **Task ID Type:** The `id` field for tasks has changed from an integer to a UUID string.
4.  **Task Field Rename:** The `done` field in task objects has been renamed to `completed`.
5.  **Project ID for Task Creation:** Creating a task now requires a `project_id`.
6.  **Paginated List Responses:** All list endpoints now return a paginated envelope instead of a bare array of items.

## Detailed Breaking Changes

### 1. Endpoint Prefix

All API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning and prevents conflicts with v1 endpoints.

**Before (v1):**
```
GET /tasks
```

**After (v2):**
```
GET /v2/tasks
```

### 2. Authentication Header

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported.

**Before (v1):**
```http
GET /tasks
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
GET /v2/tasks
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type

The `id` field for a task, previously an integer, is now a UUID string. This change provides more robust and globally unique identifiers for tasks.

**Before (v1 - Example: Get Task):**
```
GET /tasks/42
```

**After (v2 - Example: Get Task):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field Rename (`done` to `completed`)

The boolean field indicating the completion status of a task has been renamed from `done` to `completed`.

**Before (v1 - Example: Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 - Example: Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1 - Example: Update Task Request Body):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 - Example: Update Task Request Body):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Project ID for Task Creation

To support the new project-based task management, `project_id` is now a mandatory field when creating new tasks. Omitting it will result in an HTTP 422 error.

**Before (v1 - Example: Create Task Request Body):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Example: Create Task Request Body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses

All list endpoints (`GET /v2/tasks`) now return responses wrapped in a paginated envelope. This provides better control over large datasets and improves performance.

**Before (v1 - Example: List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 - Example: List Tasks Response):**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v2", "completed": true, "project_id": "proj_abc", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
Additionally, new query parameters `cursor` and `limit` are available for pagination.

**Before (v1):**
No pagination parameters.

**After (v2 - Example: List Tasks with pagination):**
```
GET /v2/tasks?cursor=cursor_xyz&limit=50
```

## Migration Checklist

1.  **Update Endpoint Paths:** Change all API endpoint calls to include the `/v2/` prefix.
2.  **Adjust Authentication:** Modify your authentication logic to use the `Authorization: Bearer <your_api_token>` header instead of `X-Auth-Token`.
3.  **Handle Task ID Type:** Update any code that stores, retrieves, or processes task IDs to expect UUID strings instead of integers.
4.  **Rename `done` to `completed`:** Replace all occurrences of the `done` field with `completed` in your task objects and API request bodies.
5.  **Add `project_id` to Task Creation:** Ensure all task creation requests include a valid `project_id` in the request body.
6.  **Refactor List Responses:** Adapt your code to parse the new paginated envelope structure for list endpoints, accessing items via the `items` array. Implement pagination logic using `cursor` and `limit` query parameters as needed.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command.

```bash
# This is a placeholder command. Please refer to the official Zrb v2 release
# notes or documentation for the exact upgrade command for your installation method.
# For a Python-based installation using pipx, it might look like:
# pipx upgrade zrb-llm-evaluator
# For a direct pip installation:
pip install --upgrade zrb
```
