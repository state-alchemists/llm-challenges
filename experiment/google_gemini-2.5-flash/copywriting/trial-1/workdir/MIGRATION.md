# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 is a major release introducing significant improvements, including support for projects, enhanced pagination, and a more robust authentication mechanism. This guide will walk you through the necessary changes to migrate your existing v1 integrations to v2.

## Breaking Changes

This section details every breaking change in Zrb CLI v2. Please review these carefully and update your code accordingly.

### 1. Endpoint Prefix Change: `/v2/`

All API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning clarity and allows for backward compatibility with v1 routes (though v1 is deprecated).

**Before (v1)**:
```
GET /tasks
```

**After (v2)**:
```
GET /v2/tasks
```

This change applies to all endpoints: `/tasks`, `/tasks/{id}`.

### 2. Authentication Header Update

The authentication mechanism has been updated for improved security and standardization. The `X-Auth-Token` header is no longer supported.

**Before (v1)**:
```http
X-Auth-Token: <your_api_key>
```

**After (v2)**:
```http
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will now result in an HTTP `401 Unauthorized` error.

### 3. Task ID Type Changed to UUID

Task identifiers (IDs) have transitioned from simple integers to UUID strings. This provides greater uniqueness and scalability for task management.

**Before (v1) Task Object**:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Task Object**:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

When fetching or updating tasks, ensure you are passing a UUID string as the ID.

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed for clearer semantics.

**Before (v1) Update Task Request**:
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Update Task Request**:
```json
{
  "title": "Updated title",
  "completed": true
}
```

Accessing or setting the `done` field in v2 will no longer work as expected. Update your code to use `completed` instead.

### 5. Task Creation Requires `project_id`

In v2, all tasks must belong to a project. Therefore, `project_id` is now a mandatory field when creating a new task.

**Before (v1) Create Task Request**:
```json
{
  "title": "New task title"
}
```

**After (v2) Create Task Request**:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` during task creation will result in an HTTP `422 Unprocessable Entity` error.

### 6. List Endpoints Return a Paginated Envelope

To support larger datasets and efficient fetching, all list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of items.

**Before (v1) List Tasks Response**:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) List Tasks Response**:
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

You will need to adapt your code to extract the `items` array from the response and handle pagination using the `next_cursor` and `limit` query parameters.

## Migration Checklist

Follow these steps to migrate your Zrb CLI integration to v2:

1.  [ ] **Update CLI Version**: Upgrade your Zrb CLI to the latest v2 version.
2.  [ ] **Endpoint Paths**: Change all API endpoint calls from `/tasks` to `/v2/tasks`.
3.  [ ] **Authentication**: Update your authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
4.  [ ] **Task ID Handling**: Modify your code to expect and send UUID strings for task IDs instead of integers.
5.  [ ] **`done` to `completed`**: Rename all references to the `done` field in task objects to `completed`.
6.  [ ] **Project ID for Creation**: Ensure `project_id` is included in all new task creation requests.
7.  [ ] **Paginated Responses**: Adjust your list endpoint parsing to handle the new paginated envelope structure, accessing task items via the `items` field. Implement logic for handling `next_cursor` for subsequent pages.

## Upgrade Command

To upgrade your Zrb CLI to v2, run the following command:

```bash
zrb upgrade --to v2
```
