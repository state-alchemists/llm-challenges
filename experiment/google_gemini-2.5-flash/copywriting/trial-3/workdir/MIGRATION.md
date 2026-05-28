# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your existing Zrb CLI integrations from v1 to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, but also includes several breaking changes that require your attention.

## Table of Contents
- [Authentication Changes](#authentication-changes)
- [Endpoint Path Prefix](#endpoint-path-prefix)
- [Task ID Type Change](#task-id-type-change)
- [Task Field Renames](#task-field-renames)
- [Required `project_id` for Task Creation](#required-project_id-for-task-creation)
- [Paginated List Responses](#paginated-list-responses)
- [Migration Checklist](#migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Authentication Changes

The authentication header has changed from a custom `X-Auth-Token` to a standard `Authorization: Bearer` token. Requests using the old header will now receive an HTTP 401 error.

### Before (v1)
```
X-Auth-Token: <your_api_key>
```

### After (v2)
```
Authorization: Bearer <your_api_token>
```

---

## Endpoint Path Prefix

All API endpoints are now prefixed with `/v2/`. This applies to all task-related operations.

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

## Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects how you reference tasks in `GET`, `PUT`, and `DELETE` requests.

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
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
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```
```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Task Field Renames

The `done` boolean field in the Task object has been renamed to `completed` for clarity. This impacts task object deserialization and update requests.

### Before (v1)
```json
{
  "id": 42,
  "title": "Ship v1",
  "done": true,
  "created_at": "..."
}
```
```json
{
  "done": true
}
```
(Request body for `PUT /tasks/{id}`)

### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v2",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "..."
}
```
```json
{
  "completed": true
}
```
(Request body for `PUT /v2/tasks/{id}`)

---

## Required `project_id` for Task Creation

When creating new tasks, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 error.

### Before (v1)
```json
{
  "title": "New task title"
}
```
(Request body for `POST /tasks`)

### After (v2)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
(Request body for `POST /v2/tasks`)

---

## Paginated List Responses

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope instead of a bare array of items. The response includes `items`, `total`, and `next_cursor` for fetching subsequent pages.

### Before (v1)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
(Response for `GET /tasks`)

### After (v2)
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
(Response for `GET /v2/tasks`. Use `?cursor=<next_cursor>` to fetch the next page.)

---

## Migration Checklist

1.  [ ] **Update Authentication:** Change `X-Auth-Token` header to `Authorization: Bearer <your_api_token>`.
2.  [ ] **Adjust Endpoint Paths:** Prefix all `/tasks` endpoints with `/v2/`.
3.  [ ] **Migrate Task IDs:** Update all stored task IDs and code referencing them to use UUID strings instead of integers.
4.  [ ] **Rename `done` to `completed`:** Update your Task object models and any `PUT` request bodies to use `completed` instead of `done`.
5.  [ ] **Add `project_id` to Task Creation:** Ensure all `POST /v2/tasks` requests include a `project_id` in the request body.
6.  [ ] **Handle Paginated Responses:** Update code that processes list endpoint responses to expect and parse the paginated envelope (`items`, `total`, `next_cursor`).

## Upgrade Command

To ensure you have the latest Zrb CLI, run:

```bash
zrb upgrade
```