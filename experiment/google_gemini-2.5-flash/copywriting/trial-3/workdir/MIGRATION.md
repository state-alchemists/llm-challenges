# Zrb CLI API v1 to v2 Migration Guide

This guide outlines the necessary steps to migrate your applications from Zrb CLI API v1 to v2. Version 2 introduces significant improvements in authentication, data modeling, and API structure, which involve several breaking changes.

## Breaking Changes

### 1. API Endpoint Prefix Changed

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

**Migration:** Update all API request URLs to include the `/v2/` prefix.

### 2. Authentication Header Changed

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard `Authorization: Bearer` token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

**Migration:** Replace `X-Auth-Token` with `Authorization: Bearer` in your request headers. Requests using the old header will receive an HTTP 401 Unauthorized response.

### 3. Task `id` Type Changed

The `id` field for Task objects has changed from an integer to a UUID string.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Migration:** Update any code that stores, parses, or uses Task `id`s to handle UUID strings instead of integers. This affects `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}`.

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion status has been renamed from `done` to `completed`.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration:** Replace all references to the `done` field with `completed` when creating or updating tasks.

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory.

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

**Migration:** Ensure all `POST /v2/tasks` requests include a `project_id` in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of task objects.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Migration:** Adjust your code to parse the `items` array from the response envelope. Implement logic to handle pagination using the `next_cursor` field and the `cursor` query parameter for subsequent requests.

## Migration Checklist

1.  [ ] Update all API endpoint URLs to include the `/v2/` prefix.
2.  [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer`.
3.  [ ] Modify code to handle Task `id` as a UUID string instead of an integer.
4.  [ ] Rename all references to the `done` field to `completed`.
5.  [ ] Ensure all `POST /v2/tasks` requests include a `project_id` in the request body.
6.  [ ] Update code to parse list endpoint responses from the `items` array within the new paginated envelope.
7.  [ ] Implement pagination logic for list endpoints using `cursor` and `limit` query parameters.

## Upgrade Command

To ensure you have the latest Zrb CLI, run the following command:

```bash
zrb upgrade
```
