# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides a clear path for migrating your existing v1 integrations. Version 2 brings significant improvements, including project support, enhanced pagination, and stricter authentication, which necessitate updates to your code.

## Breaking Changes and Migration Steps

### 1. Endpoint Prefix Change

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

**Migration:** Update all your API request paths to include the `/v2/` prefix.

### 2. Authentication Header Update

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`. Requests using the old header will receive an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Migration:** Modify your authentication mechanism to use the new `Authorization: Bearer` header format.

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Migration:** Update your code to handle `id` as a string (UUID) instead of an integer when parsing task objects or constructing requests that reference a task ID (e.g., `GET /v2/tasks/{id}`).

### 4. Task Field Renaming: `done` to `completed`

The `done` boolean field in the Task object has been renamed to `completed`.

**Before (v1) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) - Update Task Request Body:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration:** Replace all references to `done` with `completed` in your code, particularly when creating or updating task objects.

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

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

**Migration:** Ensure all task creation requests include a valid `project_id`.

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of items.

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
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_a", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v1", "completed": true, "project_id": "proj_b", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Migration:** Adjust your code to access the actual task items from the `items` field within the response envelope. Implement pagination logic using the `next_cursor` and `cursor` query parameter if you need to fetch subsequent pages.

## Migration Checklist

To successfully migrate your Zrb CLI integration to v2, follow these steps:

1.  [ ] **Update API Endpoints**: Prefix all Zrb API endpoint paths with `/v2/`.
2.  [ ] **Change Authentication Header**: Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>` for all requests.
3.  [ ] **Handle UUID Task IDs**: Update any code that stores, retrieves, or processes task IDs to expect and work with UUID strings instead of integers.
4.  [ ] **Rename `done` to `completed`**: Globally replace the `done` field with `completed` in your task object models and any API requests (especially PUT/POST).
5.  [ ] **Add `project_id` to Task Creation**: Modify task creation requests to include a `project_id` in the request body.
6.  [ ] **Adjust for Paginated List Responses**: Update code that consumes list endpoint responses to parse the paginated envelope, accessing items via the `items` field. Implement pagination if necessary.
7.  [ ] **Test Your Integration**: Thoroughly test all Zrb CLI interactions after applying the changes.

## Upgrade Command

To upgrade your Zrb CLI to v2, run the following command:

```bash
zrb upgrade --version v2
```
