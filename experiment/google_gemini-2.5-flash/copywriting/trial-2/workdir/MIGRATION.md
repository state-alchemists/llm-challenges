
# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps and breaking changes when migrating your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements, including project support, enhanced authentication, and pagination, but requires updates to your existing integrations.

## Breaking Changes

The following changes are breaking and require immediate attention when upgrading.

### 1. New Endpoint Prefix

All API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning and allows for future API evolution.

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

### 2. Authentication Header Change

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is replaced by a standard `Authorization: Bearer` token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

Task identifiers (`id`) have changed from integer type to UUID strings. This provides greater uniqueness and scalability.

**Before (v1) - Example GET request:**
```http
GET /tasks/123
```

**After (v2) - Example GET request:**
```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed` for better clarity.

**Before (v1) - Example Update Task request body:**
```json
{
  "title": "Finish report",
  "done": true
}
```

**After (v2) - Example Update Task request body:**
```json
{
  "title": "Finish report",
  "completed": true
}
```

### 5. Task Creation Requires `project_id`

With the introduction of projects in v2, every new task must now be associated with a `project_id`. This field is mandatory during task creation.

**Before (v1) - Example Create Task request body:**
```json
{
  "title": "New marketing campaign"
}
```

**After (v2) - Example Create Task request body:**
```json
{
  "title": "New marketing campaign",
  "project_id": "marketing_project_id_123"
}
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response object instead of a bare array of items. This new structure includes metadata like `total` items and `next_cursor` for efficient pagination.

**Before (v1) - Example List Tasks response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - Example List Tasks response:**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj-a", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj-b", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch subsequent pages, use the `next_cursor` value as a query parameter:

`GET /v2/tasks?cursor=cursor_xyz`

## Migration Checklist

Follow these steps to migrate your existing v1 integrations to v2:

1.  **Update Endpoint Paths**: Change all `/tasks` endpoint calls to `/v2/tasks`.
2.  **Revise Authentication**: Switch from `X-Auth-Token` to `Authorization: Bearer <your_api_token>` in all API requests.
3.  **Adapt ID Handling**: Update your code to handle task `id`s as UUID strings instead of integers. This will affect `GET`, `PUT`, and `DELETE` operations on individual tasks.
4.  **Rename `done` Field**: Replace all occurrences of the `done` field with `completed` when creating or updating tasks.
5.  **Provide `project_id`**: Ensure that all new task creation requests include a valid `project_id` in the request body.
6.  **Adjust List Response Parsing**: Update your code to parse the new paginated envelope structure for all list endpoints. Access task items via the `items` array.

## Upgrade Command

To upgrade your Zrb CLI to version 2, run the following command:

```bash
npm install -g zrb@latest
```

(Assuming Zrb CLI is distributed via npm. Adjust if different.)
