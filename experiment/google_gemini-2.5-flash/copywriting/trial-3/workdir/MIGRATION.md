# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides a step-by-step process to migrate your applications from v1.

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`.

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

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer <token>`. Requests using the old header will receive an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

The `id` field for Task objects has changed its type from an integer to a UUID string. This affects all endpoints that interact with task IDs, such as `GET /tasks/{id}`, `PUT /tasks/{id}`, and `DELETE /tasks/{id}`.

**Before (v1) Task Object Example:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Task Object Example:**
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

The boolean field `done` in the Task object has been renamed to `completed`. This affects task creation and update requests, as well as the structure of returned Task objects.

**Before (v1) Update Task Request:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Update Task Request:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. `project_id` Required for Task Creation

When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

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

### 6. Paginated List Responses

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of tasks. The response includes `items`, `total`, and `next_cursor` fields.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, use the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

## Migration Checklist

1.  [ ] **Update endpoint paths:** Change all `/tasks` to `/v2/tasks`.
2.  [ ] **Modify authentication:** Replace `X-Auth-Token` header with `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID handling:** Update any code that expects integer task IDs to handle UUID strings instead.
4.  [ ] **Rename `done` field:** Replace all occurrences of `done` with `completed` in Task objects (creation, updates, and parsing responses).
5.  [ ] **Add `project_id` to task creation:** Ensure all new task creation requests include a valid `project_id`.
6.  [ ] **Update list response parsing:** Adapt code to parse the new paginated envelope structure for list endpoints, accessing items via the `items` array.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
# This is a placeholder command.
# Please replace it with the actual Zrb CLI upgrade command.
# Example: pip install --upgrade zrb-cli
```
