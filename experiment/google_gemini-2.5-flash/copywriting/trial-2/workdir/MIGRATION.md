# Zrb CLI v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides a clear path for migrating your existing v1 integrations. v2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication.

## Table of Contents

1.  [Breaking Change: Endpoint Prefix](#breaking-change-endpoint-prefix)
2.  [Breaking Change: Authentication Header](#breaking-change-authentication-header)
3.  [Breaking Change: Task `id` Type](#breaking-change-task-id-type)
4.  [Breaking Change: Task Field `done` Renamed to `completed`](#breaking-change-task-field-done-renamed-to-completed)
5.  [Breaking Change: `project_id` Required for Task Creation](#breaking-change-project_id-required-for-task-creation)
6.  [Breaking Change: List Endpoints Return Paginated Envelope](#breaking-change-list-endpoints-return-paginated-envelope)
7.  [Migration Checklist](#migration-checklist)
8.  [Upgrade Command](#upgrade-command)

---

## Breaking Change: Endpoint Prefix

All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints (without `/v2/`) will no longer work.

### Before (v1)

```bash
GET /tasks
POST /tasks
GET /tasks/{id}
```

### After (v2)

```bash
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

## Breaking Change: Authentication Header

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. You must now use a Bearer token in the `Authorization` header.

Requests using `X-Auth-Token` will receive an HTTP 401 Unauthorized response.

### Before (v1)

```http
X-Auth-Token: <your_api_key>
```

```bash
curl -X GET \
  -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.com/tasks
```

### After (v2)

```http
Authorization: Bearer <your_api_token>
```

```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.com/v2/tasks
```

## Breaking Change: Task `id` Type

The `id` field for Task objects has changed from an integer to a UUID string. This impacts all endpoints that reference tasks by their ID.

### Before (v1)

Task Object:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

Get Task Example:
```bash
curl -X GET \
  -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.com/tasks/42
```

### After (v2)

Task Object:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Get Task Example:
```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Breaking Change: Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This affects task creation and update operations.

### Before (v1)

Create Task Request Body:
```json
{
  "title": "New task title"
}
```

Update Task Request Body:
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2)

Create Task Request Body:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Update Task Request Body:
```json
{
  "title": "Updated title",
  "completed": true
}
```

## Breaking Change: `project_id` Required for Task Creation

When creating new tasks, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity error.

### Before (v1)

```bash
curl -X POST \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "My new task"}' \
  https://api.zrb.com/tasks
```

### After (v2)

```bash
curl -X POST \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "My new task", "project_id": "proj_abc123"}' \
  https://api.zrb.com/v2/tasks
```

## Breaking Change: List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of items. The response includes `items`, `total`, and `next_cursor` fields.

To fetch subsequent pages, use the `next_cursor` value in the `cursor` query parameter.

### Before (v1)

List Tasks Response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)

List Tasks Response:
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetching the next page:
```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.com/v2/tasks?cursor=cursor_xyz&limit=20"
```

## Migration Checklist

1.  [ ] **Update all endpoint paths** to include the `/v2/` prefix.
2.  [ ] **Change authentication header** from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Update all task ID references** from integers to UUID strings.
4.  [ ] **Rename the `done` field to `completed`** in task creation and update requests, and when processing task objects.
5.  [ ] **Add `project_id`** as a required field in all task creation requests.
6.  [ ] **Adjust parsing logic for list endpoints** to handle the new paginated envelope structure (`items`, `total`, `next_cursor`). Implement pagination logic using the `cursor` and `limit` query parameters.

## Upgrade Command

To ensure you have the latest Zrb CLI, run:

```bash
pip install --upgrade zrb
```
