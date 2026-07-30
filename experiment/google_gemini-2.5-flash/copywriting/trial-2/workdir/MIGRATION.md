# Zrb CLI v1 to v2 Migration Guide

This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers step-by-step instructions to migrate your existing v1 integrations. v2 introduces significant enhancements, including project management, improved pagination, and a more robust authentication mechanism.

## Breaking Changes

Zrb CLI v2 includes several breaking changes that require updates to your existing code.

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`.

**Before (v1):**
```
GET /tasks
```

**After (v2):**
```
GET /v2/tasks
```

This change affects all API calls. Ensure you update your base URL or endpoint paths accordingly.

### 2. Authentication Header Update

The authentication mechanism has changed from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

Requests using the old `X-Auth-Token` header will now result in an HTTP 401 Unauthorized error. Update your client's authentication logic to use the new `Authorization: Bearer` header.

### 3. Task `id` Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This impacts any operations that involve fetching, updating, or deleting tasks by ID.

**Before (v1) Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Ensure your code handles `id` values as strings instead of integers when interacting with v2 endpoints.

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This affects both the Task object structure and the request body for updating tasks.

**Before (v1) Update Task Request:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Update Task Request:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

Update your task object parsing and creation/update logic to use `completed` instead of `done`.

### 5. Task Creation Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) Create Task Request:**
```json
{
  "title": "New task title"
}
```

**After (v2) Create Task Request:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Ensure all task creation requests include a valid `project_id`.

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response encapsulated in an envelope object, rather than a bare array of items.

**Before (v1) List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) List Tasks Response:**
```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v2", "completed": true, "project_id": "proj_xyz456", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

You will need to adjust your parsing logic to access the task items from the `items` array within the response envelope. Pagination can now be controlled using `cursor` and `limit` query parameters.

## Migration Checklist

To successfully migrate your Zrb CLI v1 integration to v2, follow these steps:

1.  **Update Endpoint Paths:** Prefix all your API endpoint calls with `/v2/`.
2.  **Revise Authentication:** Change your authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling:** Ensure your code treats Task `id`s as UUID strings, not integers.
4.  **Rename Task Completion Field:** Update all references from `done` to `completed` in your Task object models and API requests.
5.  **Add `project_id` to Task Creation:** Include the `project_id` field in all `POST /v2/tasks` requests.
6.  **Update List Response Parsing:** Modify your code to parse list responses from the `items` array within the new paginated envelope structure.
7.  **Implement Pagination (Optional):** If needed, utilize the `cursor` and `limit` query parameters for paginated list endpoints.
8.  **Test Thoroughly:** After making all changes, thoroughly test your application against the v2 API.

## Upgrade Command

To upgrade your Zrb CLI, run the following command:

```bash
zrb upgrade --to v2
```