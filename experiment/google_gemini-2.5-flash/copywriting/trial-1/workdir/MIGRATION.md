# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and provides a step-by-step migration path for developers transitioning their Zrb CLI integrations from v1 to v2.

## Breaking Changes

Zrb CLI v2 introduces several significant changes to its API, focusing on projects, improved pagination, and stricter authentication.

### 1. Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. This ensures version isolation and allows for future API evolution.

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

### 2. Authentication Header Change

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header. Requests using the old header will now result in an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

The `id` field for Task objects has changed its data type from an integer to a UUID string. This change provides better global uniqueness and avoids potential collisions in distributed systems.

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

### 4. `done` Field Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed` for improved clarity and consistency.

**Before (v1) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. `project_id` Required for Task Creation

Task creation in v2 now mandates a `project_id`. This new field allows for organizing tasks within specific projects. Omitting `project_id` during task creation will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) - Create Task Request Body:**
```json
{
  "title": "New task title"
}
```

**After (v2) - Create Task Request Body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of task objects. Instead, they return a paginated envelope that includes the items, total count, and a `next_cursor` for subsequent pages.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, include the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`. A `limit` query parameter (default 20) is also available.

## Migration Checklist

To successfully migrate your Zrb CLI integration to v2, follow these steps:

1.  **Update Endpoint Paths:** Change all `/tasks` endpoints to `/v2/tasks`.
2.  **Modify Authentication:** Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`.
3.  **Handle Task IDs:** Adjust your code to expect and handle UUID strings for task IDs instead of integers.
4.  **Rename Completion Field:** Change all references to the `done` field in Task objects and request bodies to `completed`.
5.  **Provide `project_id`:** Ensure all task creation requests (`POST /v2/tasks`) include a `project_id`.
6.  **Adapt List Endpoint Responses:** Update your parsing logic for list endpoints to handle the new paginated envelope structure. Implement pagination using the `cursor` and `limit` query parameters.

## Upgrade Command

To ensure you have the latest Zrb CLI, run the following upgrade command:

```bash
pip install --upgrade zrb-cli
```
