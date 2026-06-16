# Zrb CLI Migration Guide from v1 to v2

This migration guide outlines the breaking changes introduced in v2 of the Zrb CLI and provides developers with the necessary steps to transition from v1. 

## Breaking Changes Overview

1. All API endpoints now have a `/v2/` prefix.
2. Authentication header changed from `X-Auth-Token` to Bearer token.
3. Task `id` type changed from integer to UUID string.
4. Task field `done` renamed to `completed`.
5. Task creation now requires `project_id`.
6. List endpoints return a paginated envelope instead of a bare array.

---

## Details of Breaking Changes

### 1. Endpoint Prefix Change

All endpoints are now prefixed with `/v2/`. For example:

#### Before:
```
GET /tasks
```

#### After:
```
GET /v2/tasks
```

### 2. Authentication Header Change

The authentication method has changed:

#### Before:
```
X-Auth-Token: <your_api_key>
```

#### After:
```
Authorization: Bearer <your_api_token>
```

Requests with `X-Auth-Token` will now receive HTTP 401 Unauthorized.

### 3. Task `id` Type Change

The `id` field for tasks has changed from an integer to a UUID string.

#### Before:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Task Field Renaming

The `done` field in tasks has been renamed to `completed`.

#### Before:
```json
{
  "done": false
}
```

#### After:
```json
{
  "completed": false
}
```

### 5. Required `project_id` in Task Creation

Task creation now requires the `project_id` field. Omitting it will return HTTP 422.

#### Before:
```json
{
  "title": "New task title"
}
```

#### After:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Envelope

All list endpoints now return a paginated envelope instead of a bare array.

#### Before:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Step-by-Step Migration Checklist

1. Update all API endpoints to include the `/v2/` prefix.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update task `id` handling to use UUID strings instead of integers.
4. Rename all instances of the `done` field to `completed` in task objects.
5. Ensure all task creation requests include the `project_id` field.
6. Implement pagination for list responses and handle the new response structure.

## Upgrade Command

Run the following command to upgrade to v2:
```
npm install -g zrb@v2
```