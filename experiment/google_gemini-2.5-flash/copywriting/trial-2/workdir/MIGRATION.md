# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your existing Zrb CLI v1 integrations to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and a more secure authentication mechanism.

## Breaking Changes

### 1. API Endpoint Prefix

All API endpoints are now prefixed with `/v2/`.

**Before (v1):**
```
GET /tasks
```

**After (v2):**
```
GET /v2/tasks
```

### 2. Authentication Header

The authentication header has changed from a custom `X-Auth-Token` to a standard Bearer token in the `Authorization` header. Requests using the old header will receive an HTTP 401 Unauthorized response.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that take an `id` as a path parameter.

**Before (v1) - Get Task:**
```
GET /tasks/123
```

**After (v2) - Get Task:**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field `done` on the Task object has been renamed to `completed`. This impacts task creation and updates.

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

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity response.

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

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response wrapped in an envelope object, rather than a bare array of items. The envelope includes `items`, `total`, and `next_cursor` fields.

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
    {"id": "e5f6-7890-...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, pass `?cursor=<next_cursor>` as a query parameter.

## Migration Checklist

1.  [ ] **Update API Endpoint Paths:** Change all `/tasks` paths to `/v2/tasks`.
2.  [ ] **Switch Authentication:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
3.  [ ] **Handle Task ID Type:** Update code that generates or parses task IDs to use UUID strings instead of integers.
4.  [ ] **Rename `done` to `completed`:** Modify request and response parsing logic to use `completed` instead of `done`.
5.  [ ] **Provide `project_id` for Task Creation:** Ensure all task creation requests include a valid `project_id`.
6.  [ ] **Adjust List Endpoint Response Parsing:** Update code that processes list responses to extract items from the `items` field of the paginated envelope. Implement pagination logic using `next_cursor` if needed.

## Upgrade Command

To upgrade your Zrb CLI, run:

```bash
zrb upgrade --to v2
```
