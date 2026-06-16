# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your existing Zrb CLI v1 integrations to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication.

## Breaking Changes

### 1. API Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`.

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

### 2. Authentication Header Update

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`. Requests using the old header will receive an HTTP 401 Unauthorized error.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference tasks by ID (Get, Update, Delete).

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```
Example v1 request:
```
GET /tasks/42
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```
Example v2 request:
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. This affects Task object definitions and any update requests.

**Before (v1) - Task Object:**
```json
{
  "id": 1,
  "title": "Ship v1",
  "done": true
}
```
**Before (v1) - Update Request:**
```json
{
  "done": true
}
```

**After (v2) - Task Object:**
```json
{
  "id": "...",
  "title": "Ship v2",
  "completed": true
}
```
**After (v2) - Update Request:**
```json
{
  "completed": true
}
```

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity response.

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

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `/v2/tasks`) now return a paginated response envelope instead of a bare array of items. The response includes `items`, `total`, and `next_cursor` for pagination.

**Before (v1) - Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - Response:**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, append `?cursor=<next_cursor>` to your request. You can also use `?limit=<N>` to control the page size (default 20).

## Migration Checklist

1.  [ ] Update all API endpoint paths to include the `/v2/` prefix.
2.  [ ] Change your authentication mechanism from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  [ ] Adjust your code to handle Task `id`s as UUID strings instead of integers.
4.  [ ] Rename all references to the `done` field to `completed` in Task objects and update requests.
5.  [ ] Ensure all new Task creation requests include a `project_id` in the request body.
6.  [ ] Modify code interacting with list endpoints to parse the new paginated response envelope and handle `items`, `total`, and `next_cursor` for pagination.

## Upgrade Command

To upgrade your Zrb CLI installation:

```bash
zrb upgrade --version 2
```
