# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides instructions and examples to help you migrate your existing v1 applications. Zrb CLI v2 introduces significant improvements, including project support, enhanced pagination, and a more robust authentication mechanism.

## Breaking Changes

### 1. All Endpoints are now Prefixed with `/v2/`

All API endpoints have been moved under the `/v2/` path. This change applies to all task-related operations.

**Before (v1)**
```
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication Header Changed

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header.

**Before (v1)**
```
X-Auth-Token: <your_api_key>
```

**After (v2)**
```
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are no longer sequential integers but universally unique identifiers (UUIDs) represented as strings. This affects all endpoints that accept or return a task `id`.

**Before (v1)**
```json
{
  "id": 42,
  "title": "Old task"
}
```

```
GET /tasks/42
```

**After (v2)**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New task"
}
```

```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1)**
```json
{
  "id": 42,
  "title": "Buy milk",
  "done": false
}
```
Update in v1:
```json
{
  "done": true
}
```

**After (v2)**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Buy milk",
  "completed": false
}
```
Update in v2:
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, you must now include a `project_id` in the request body. This links the task to a specific project. Omitting `project_id` will result in an HTTP 422 error.

**Before (v1)**
```json
{
  "title": "New task title"
}
```

**After (v2)**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope Instead of a Bare Array

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response encapsulated within an envelope object, rather than a bare array of items. The envelope includes `items`, `total`, and `next_cursor` for pagination.

**Before (v1)**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2)**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, use the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

## Migration Checklist

To successfully upgrade your application to Zrb CLI v2, follow these steps:

1.  [ ] **Update Endpoint Paths**: Prefix all Zrb API calls with `/v2/`.
2.  [ ] **Modify Authentication Header**: Change `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling**: Update your code to expect and use UUID strings for task `id`s instead of integers.
4.  [ ] **Rename Task Completion Field**: Change all references from `done` to `completed` in your task objects and API requests.
5.  [ ] **Add `project_id` to Task Creation**: Ensure all new task creation requests include a `project_id`.
6.  [ ] **Update List Endpoint Parsing**: Adapt your code to parse the new paginated list envelope, accessing task items via the `items` array and handling pagination with `next_cursor`.

## Upgrade Command

Once you have completed the necessary code changes, upgrade your Zrb CLI installation:

```bash
zrb upgrade --to v2
```
