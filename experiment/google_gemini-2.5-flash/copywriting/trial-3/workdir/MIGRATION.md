# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides a clear path for migrating your existing v1 implementations.

## Introduction to v2

Zrb CLI v2 brings significant improvements, including projects, enhanced pagination, and a more robust authentication mechanism. To ensure a smooth transition, please review the following breaking changes carefully.

## Breaking Changes and Migration Steps

### 1. Endpoint Path Prefix

All API endpoints now require a `/v2/` prefix.

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

**Migration:** Update all your API request paths to include the `/v2/` prefix.

### 2. Authentication Header

The authentication header has changed from a custom `X-Auth-Token` to a standard `Authorization: Bearer` token.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Migration:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>` in all your API requests. Requests using the old header will receive an HTTP 401 Unauthorized response.

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This impacts fetching, updating, and deleting tasks.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Old task"
}
```
```
GET /tasks/42
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New task"
}
```
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Migration:** Ensure your application handles task IDs as UUID strings. If you were storing IDs as integers, you will need to migrate your data or adjust how you retrieve and use these IDs.

### 4. `done` Field Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`.

**Before (v1):**
```json
{
  "title": "Update title",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Update title",
  "completed": true
}
```

**Migration:** Update all task object structures and API request bodies to use `completed` instead of `done`.

### 5. `project_id` Requirement for Task Creation

Creating a new task now requires a `project_id` in the request body.

**Before (v1):**
```json
{
  "title": "New task title"
}
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration:** When creating tasks, include the `project_id` field in your request body. Omitting this field will result in an HTTP 422 Unprocessable Entity response.

### 6. Paginated List Endpoints

List endpoints (e.g., `/v2/tasks`) no longer return a bare array. Instead, they return a paginated envelope containing `items`, `total`, and `next_cursor`.

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
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj-a", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj-b", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Migration:** Adjust your code to parse the paginated envelope. To fetch subsequent pages, use the `next_cursor` value in the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

## Migration Checklist

To ensure a complete and successful migration, follow these steps:

1.  [ ] **Update CLI version:** Upgrade your Zrb CLI to v2.
2.  [ ] **Modify API endpoint paths:** Prefix all `/tasks` endpoints with `/v2/`.
3.  [ ] **Update authentication:** Change `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
4.  [ ] **Adjust Task ID handling:** Ensure your code handles Task IDs as UUID strings, not integers.
5.  [ ] **Rename `done` to `completed`:** Update all references to the task completion field.
6.  [ ] **Add `project_id` to task creation:** Include `project_id` in the request body for new tasks.
7.  [ ] **Refactor list endpoint responses:** Adapt your code to parse the new paginated envelope structure for list API calls.
8.  [ ] **Test thoroughly:** Verify all your integrations and custom scripts against the v2 API.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run:

```bash
pip install --upgrade zrb
```
