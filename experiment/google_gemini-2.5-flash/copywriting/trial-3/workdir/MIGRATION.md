# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your existing Zrb CLI v1 integrations to the new v2 API. Zrb v2 introduces significant improvements, including project support, enhanced authentication, and pagination, but comes with several breaking changes.

The audience for this guide is experienced developers already familiar with Zrb CLI v1.

## Table of Contents
1.  [API Endpoint Prefix Change](#api-endpoint-prefix-change)
2.  [Authentication Header Update](#authentication-header-update)
3.  [Task ID Type Change](#task-id-type-change)
4.  [Task Field Renamed: `done` to `completed`](#task-field-renamed-done-to-completed)
5.  [Project ID Requirement for Task Creation](#project-id-requirement-for-task-creation)
6.  [Paginated List Endpoint Responses](#paginated-list-endpoint-responses)
7.  [Migration Checklist](#migration-checklist)
8.  [Upgrade Command](#upgrade-command)

---

## 1. API Endpoint Prefix Change

All API endpoints in Zrb v2 are now prefixed with `/v2/`. This applies to all task-related operations.

### Breaking Change
The base path for all task endpoints has changed from `/` to `/v2/`.

### Before (v1)
```http
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

### After (v2)
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

## 2. Authentication Header Update

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported.

### Breaking Change
Authentication now requires a Bearer token in the `Authorization` header. Requests using `X-Auth-Token` will receive an HTTP 401 Unauthorized response.

### Before (v1)
```http
X-Auth-Token: <your_api_key>
```

### After (v2)
```http
Authorization: Bearer <your_api_token>
```

---

## 3. Task ID Type Change

The `id` field for Task objects has changed its data type.

### Breaking Change
Task `id` is now a UUID string instead of an integer. This affects all endpoints that use `id` in the path or payload.

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

```http
GET /tasks/42
```

### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 4. Task Field Renamed: `done` to `completed`

The boolean field indicating a task's completion status has been renamed.

### Breaking Change
The `done` field in the Task object has been renamed to `completed`. This affects both reading Task objects and updating their status.

### Before (v1)
```json
// Task object
{
  "id": 42,
  "title": "Buy milk",
  "done": false
}

// Update request body
{
  "done": true
}
```

### After (v2)
```json
// Task object
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Buy milk",
  "completed": false
}

// Update request body
{
  "completed": true
}
```

---

## 5. Project ID Requirement for Task Creation

Zrb v2 introduces the concept of projects, and tasks are now associated with them.

### Breaking Change
When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity response.

### Before (v1)
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2)
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. Paginated List Endpoint Responses

All list endpoints now return a paginated envelope instead of a bare array of items.

### Breaking Change
The `GET /v2/tasks` endpoint (and other list endpoints) no longer returns a direct JSON array of tasks. Instead, it returns an object containing an `items` array, `total` count, and a `next_cursor` for pagination.

### Before (v1)
```http
GET /tasks
Content-Type: application/json

[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```http
GET /v2/tasks
Content-Type: application/json

{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v1", "completed": true, "project_id": "proj_xyz", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, include the `cursor` query parameter:
```http
GET /v2/tasks?cursor=cursor_xyz
```

You can also specify a `limit` per page:
```http
GET /v2/tasks?limit=50
```

---

## 7. Migration Checklist

Follow these steps to migrate your Zrb CLI v1 integration to v2:

- [ ] **Update all endpoint paths**: Change all instances of `/tasks` to `/v2/tasks`.
- [ ] **Change authentication header**: Replace `X-Auth-Token` with `Authorization: Bearer` and update your API key to a Bearer token.
- [ ] **Adjust Task ID handling**: Ensure your code can handle UUID strings for task IDs instead of integers. Update any data storage or parsing logic accordingly.
- [ ] **Rename task field `done` to `completed`**: Update all references to `done` in your code, both when reading task objects and when sending update requests.
- [ ] **Add `project_id` to task creation**: Modify your task creation logic to include a mandatory `project_id` in the request body. You will need to determine or retrieve the appropriate project ID for new tasks.
- [ ] **Adapt to paginated list responses**: Update your code to parse the paginated envelope for list endpoints. Access tasks via the `items` array and handle `next_cursor` for fetching additional pages.

---

## 8. Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run the following command:

```bash
zrb upgrade --version v2
```
