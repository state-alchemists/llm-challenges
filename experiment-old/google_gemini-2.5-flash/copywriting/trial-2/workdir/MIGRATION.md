# Zrb CLI v2 Migration Guide

Zrb CLI v2 is here, bringing significant improvements, including project support, enhanced pagination, and stricter authentication. This guide outlines all breaking changes from v1 to v2 and provides step-by-step instructions to help you migrate your existing applications.

We've focused on clarity and consistency in v2 to provide a more robust and scalable API for your task management needs.

## Breaking Changes

Zrb CLI v2 introduces several breaking changes that require updates to your code. Each change is detailed below with before/after examples.

### 1. All Endpoints Now Require `/v2/` Prefix

All API endpoints in v2 are now prefixed with `/v2/`. Requests to v1 endpoints without this prefix will fail.

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

### 2. Authentication Header Changed

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. You must now use a `Bearer` token in the `Authorization` header.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will now return an HTTP 401 Unauthorized response.

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects is no longer an auto-assigned integer. It is now a UUID string, providing a more robust and globally unique identifier. This impacts fetching, updating, and deleting tasks.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Impacted Endpoints (example `Get Task`):**

**Before (v1):**
```
GET /tasks/42
```

**After (v2):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed` for better clarity and consistency.

**Before (v1) - `Update Task` Request Body:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) - `Update Task` Request Body:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

In v2, tasks are now associated with projects. When creating a new task, you must include a `project_id` in the request body. Omitting `project_id` will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) - `Create Task` Request Body:**
```json
{
  "title": "New task title"
}
```

**After (v2) - `Create Task` Request Body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return results wrapped in a paginated envelope object, rather than a bare array of items. This change supports efficient pagination and provides additional metadata.

**Before (v1) - `List Tasks` Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - `List Tasks` Response:**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj-a", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj-a", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, use the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=<next_cursor>`. A `limit` query parameter is also available to control the number of results per page (default 20).

## Migration Checklist

Follow these steps to migrate your application to Zrb CLI v2:

1.  **Update Endpoint Paths:** Change all API calls to include the `/v2/` prefix (e.g., `/tasks` to `/v2/tasks`).
2.  **Modify Authentication:** Switch from `X-Auth-Token` header to `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling:** Update your code to expect and use UUID strings for task IDs instead of integers.
4.  **Rename `done` to `completed`:** Replace all occurrences of the `done` field with `completed` in your Task object models and API request bodies.
5.  **Add `project_id` to Task Creation:** Ensure all `Create Task` requests include a `project_id` in the request body. You may need to introduce project management into your application if you haven't already.
6.  **Handle Paginated Responses:** Update your code to parse list endpoint responses from the new paginated envelope structure (`items`, `total`, `next_cursor`) instead of a bare array. Implement logic for cursor-based pagination if required.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
zrb upgrade --version 2
```
