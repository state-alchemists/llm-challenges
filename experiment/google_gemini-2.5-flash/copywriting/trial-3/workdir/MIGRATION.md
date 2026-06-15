# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces significant enhancements, including support for projects, improved pagination, and a more secure authentication mechanism. This guide outlines the breaking changes from v1 and provides a step-by-step process for migrating your applications.

The goal is to provide a smooth transition, ensuring your existing integrations can be updated efficiently.

## Breaking Changes

### 1. All Endpoints are now prefixed with `/v2/`

All API routes have been updated to include a `/v2/` prefix. Requests to v1 endpoints without this prefix will no longer be routed.

**Before (v1):**
```bash
curl -X GET https://api.zrb.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl -X GET https://api.zrb.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

### 2. Authentication Header Changed

The authentication mechanism has been updated for enhanced security. The `X-Auth-Token` header is deprecated and will result in an `HTTP 401 Unauthorized` error. You must now use a `Bearer` token in the `Authorization` header.

**Before (v1):**
```bash
X-Auth-Token: <your_api_key>
```

**After (v2):**
```bash
Authorization: Bearer <your_api_token>
```

**Example (v1 `GET /tasks`):**
```bash
curl -X GET https://api.zrb.com/tasks \
  -H "X-Auth-Token: your_v1_api_key"
```

**Example (v2 `GET /v2/tasks`):**
```bash
curl -X GET https://api.zrb.com/v2/tasks \
  -H "Authorization: Bearer your_v2_api_token"
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects is no longer an integer. It is now a UUID string, providing a more robust and globally unique identifier.

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2 Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

This change affects all endpoints that accept or return a task `id` (e.g., `GET /tasks/{id}`, `PUT /tasks/{id}`, `DELETE /tasks/{id}`).

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating the completion status of a task has been renamed from `done` to `completed`.

**Before (v1 `PUT /tasks/{id}` request body):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 `PUT /v2/tasks/{id}` request body):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

In v2, tasks are associated with projects. When creating a new task, you must now provide a `project_id` in the request body. Omitting this field will result in an `HTTP 422 Unprocessable Entity` error.

**Before (v1 `POST /tasks` request body):**
```json
{
  "title": "New task title"
}
```

**After (v2 `POST /v2/tasks` request body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope Instead of a Bare Array

All list endpoints (e.g., `GET /v2/tasks`) now return results wrapped in a paginated envelope object, rather than a bare array of items. This new structure facilitates efficient pagination.

**Before (v1 `GET /tasks` response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 `GET /v2/tasks` response):**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-890b-cdef-1234567890ab", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, use the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

## Migration Checklist

To migrate your application from Zrb CLI v1 to v2, follow these steps:

1.  **Update Endpoint Paths:** Change all API endpoint URLs from `/tasks` to `/v2/tasks`.
2.  **Revise Authentication:** Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`.
3.  **Handle Task ID Type:** Adjust your code to expect and work with UUID strings for task `id`s instead of integers.
4.  **Rename `done` Field:** Update any references to the `done` field to `completed` in your Task objects and API requests.
5.  **Add `project_id` to Task Creation:** Ensure all `POST /v2/tasks` requests include a `project_id` in the request body.
6.  **Adapt to Paginated Responses:** Modify your list endpoint consumers to parse the new paginated envelope structure, accessing items via the `items` array and handling pagination with `next_cursor`.

## Upgrade Command

To upgrade your Zrb CLI installation, run:

```bash
zrb upgrade --to v2
```
