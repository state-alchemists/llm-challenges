# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements in authentication, data modeling, and API structure.

## What's New in v2

Zrb CLI v2 introduces the concept of projects, enhanced pagination for listing resources, and a more secure authentication mechanism. Several existing fields and conventions have been updated to provide a more robust and scalable API.

---

## Breaking Changes

### 1. Endpoint Path Prefix

All API endpoints are now prefixed with `/v2/`. This ensures versioning and allows for parallel operation with v1 during a migration period.

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

### 2. Authentication Header

The authentication header has changed from `X-Auth-Token` to a standard `Authorization: Bearer` token. Requests using the old header will result in an HTTP 401 Unauthorized error.

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

### 3. Task ID Type Change

The `id` field for Task objects has changed its type from an integer to a UUID string. This provides a more robust and universally unique identifier for tasks.

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

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

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

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting this field will result in an HTTP 422 Unprocessable Entity response.

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

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of items. This new structure includes pagination metadata like `total` and `next_cursor`.

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
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_a", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_a", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, use the `next_cursor` value as a query parameter:

```
GET /v2/tasks?cursor=cursor_xyz
```

---

## Migration Checklist

1. [ ] **Update API Key Handling:** Change your authentication mechanism from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
2. [ ] **Adjust Endpoint Paths:** Prefix all Zrb CLI API endpoint calls with `/v2/`.
3. [ ] **Review Task ID Usage:** Update any code that handles task IDs, as they are now UUID strings instead of integers.
4. [ ] **Rename `done` to `completed`:** Replace all instances of the `done` field with `completed` in your task objects and API requests.
5. [ ] **Add `project_id` to Task Creation:** Ensure all task creation requests include a valid `project_id`.
6. [ ] **Refactor List Endpoint Responses:** Update your code to parse the new paginated envelope structure for all list endpoints. Access items via the `items` array and handle `next_cursor` for pagination.
7. [ ] **Test Thoroughly:** After making the changes, run your comprehensive test suite to ensure all functionalities are working as expected with Zrb CLI v2.

---

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
zrb upgrade --version 2.0.0
```
